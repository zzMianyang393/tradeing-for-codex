from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import BacktestConfig
from exchange import DryRunExchange, ExchangeError, OrderResult
from executor import ExecutionRequest, Executor
from risk_manager import RiskManager
from runner import RunInput, TradingRunner, main
from state_db import StateDB
from strategy import Signal


def _bars(atr_pct: float = 0.02):
    bar = MagicMock()
    bar.atr_pct = atr_pct
    bar.close = 100.0
    return [bar]


class TestTradingRunner(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = StateDB(Path(self._tmp.name) / "state.db")
        self.config = BacktestConfig(
            rm_max_single_position_pct=1.0,
            rm_max_total_position_pct=0.80,
            rm_min_liquidation_distance_pct=0.05,
        )
        self.risk_manager = RiskManager(self.config)
        self.exchange = DryRunExchange()
        self.executor = Executor(self.exchange, self.risk_manager, self.db, self.config)
        self.runner = TradingRunner(self.config, self.executor, self.db)

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def test_run_once_executes_signal_syncs_and_snapshots_account(self):
        signal = Signal("BTC-USDT-SWAP", 1, 3.5, "range", "range_revert_long")
        request = ExecutionRequest.from_signal(signal, price=100.0, notional=10.0, margin=1.0, leverage=10.0)

        report = self.runner.run_once(
            RunInput(
                equity=100.0,
                current_step=1,
                current_prices={"BTC-USDT-SWAP": 100.0},
                bars_by_symbol={"BTC-USDT-SWAP": _bars()},
                signal_requests=[request],
            )
        )

        self.assertEqual(1, report.executed_orders)
        self.assertTrue(report.sync_consistent)
        self.assertEqual(1, report.open_positions)
        self.assertEqual(1, len(self.db.get_account_history()))

    def test_run_once_manages_existing_position_before_new_signals(self):
        self.db.save_position(
            "ETH-USDT-SWAP",
            "long",
            entry_price=100.0,
            qty=0.1,
            notional=10.0,
            margin=1.0,
            leverage=10.0,
            stop_loss=95.0,
            take_profit=105.0,
        )
        self.exchange.positions = [{"symbol": "ETH-USDT-SWAP", "direction": "long"}]

        report = self.runner.run_once(
            RunInput(
                equity=100.0,
                current_step=2,
                current_prices={"ETH-USDT-SWAP": 106.0},
                bars_by_symbol={"ETH-USDT-SWAP": _bars()},
            )
        )

        self.assertEqual(1, report.closed_positions)
        self.assertEqual(0, report.open_positions)
        self.assertEqual(1, self.db.count_trades())


class TestRunnerCli(unittest.TestCase):
    def test_status_outputs_json_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.snapshot_account(equity=100.0, available_margin=90.0, used_margin=10.0)
            finally:
                db.close()
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                code = main(["--status", "--db", str(db_path)])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertEqual(100.0, payload["equity"])
            self.assertEqual(0, payload["open_positions"])

    def test_once_creates_account_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--once", "--db", str(db_path), "--equity", "25"])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertEqual(25.0, payload["equity"])
            db = StateDB(db_path)
            try:
                self.assertEqual(1, len(db.get_account_history()))
            finally:
                db.close()

    def test_reconcile_reports_inconsistent_local_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.save_position("BTC-USDT-SWAP", "long", 100.0, 0.1, 10.0, 1.0, 10.0)
            finally:
                db.close()

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--reconcile", "--db", str(db_path)])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["consistent"])
            self.assertEqual(1, len(payload["local_only"]))

    def test_reconcile_can_compare_local_positions_with_okx_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.save_position("BTC-USDT-SWAP", "long", 100.0, 0.1, 10.0, 1.0, 10.0)
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_positions.return_value = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange) as cls:
                with contextlib.redirect_stdout(output):
                    code = main(["--reconcile", "--exchange", "okx", "--db", str(db_path)])

            self.assertEqual(0, code)
            cls.assert_called_once_with("key", "secret", "passphrase", sandbox=True)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["consistent"])
            self.assertEqual(1, len(payload["matches"]))

    def test_reconcile_okx_returns_error_when_credentials_are_missing(self):
        output = io.StringIO()
        env = {
            "OKX_API_KEY": "",
            "OKX_API_SECRET": "",
            "OKX_API_PASSPHRASE": "",
        }

        with patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(output):
            code = main(["--reconcile", "--exchange", "okx"])

        self.assertEqual(2, code)
        payload = json.loads(output.getvalue())
        self.assertIn("OKX_API_KEY", payload["error"])

    def test_reconcile_okx_returns_json_error_when_exchange_fails(self):
        fake_exchange = MagicMock()
        fake_exchange.get_positions.side_effect = ExchangeError("OKX error 500: unavailable")
        env = {
            "OKX_API_KEY": "key",
            "OKX_API_SECRET": "secret",
            "OKX_API_PASSPHRASE": "passphrase",
        }
        output = io.StringIO()

        with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
            with contextlib.redirect_stdout(output):
                code = main(["--reconcile", "--exchange", "okx"])

        self.assertEqual(1, code)
        payload = json.loads(output.getvalue())
        self.assertIn("unavailable", payload["error"])

    def test_loop_runs_configured_iterations(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([
                    "--loop",
                    "--iterations",
                    "3",
                    "--interval",
                    "0",
                    "--db",
                    str(db_path),
                    "--equity",
                    "25",
                ])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertEqual(3, payload["iterations"])
            self.assertEqual(25.0, payload["equity"])
            db = StateDB(db_path)
            try:
                self.assertEqual(3, len(db.get_account_history()))
            finally:
                db.close()

    def test_okx_check_uses_env_credentials_and_outputs_read_only_status(self):
        fake_exchange = MagicMock()
        fake_exchange.get_account_balance.return_value.equity = 100.5
        fake_exchange.get_account_balance.return_value.available_margin = 80.0
        fake_exchange.get_account_balance.return_value.used_margin = 20.5
        fake_exchange.get_ticker.return_value.symbol = "BTC-USDT-SWAP"
        fake_exchange.get_ticker.return_value.last = 50100.0
        fake_exchange.get_ticker.return_value.bid = 50099.0
        fake_exchange.get_ticker.return_value.ask = 50101.0
        fake_exchange.get_positions.return_value = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]
        env = {
            "OKX_API_KEY": "key",
            "OKX_API_SECRET": "secret",
            "OKX_API_PASSPHRASE": "passphrase",
        }
        output = io.StringIO()

        with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange) as cls:
            with contextlib.redirect_stdout(output):
                code = main(["--okx-check", "--okx-symbol", "BTC-USDT-SWAP"])

        self.assertEqual(0, code)
        cls.assert_called_once_with("key", "secret", "passphrase", sandbox=True)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["okx_check"])
        self.assertEqual("BTC-USDT-SWAP", payload["ticker"]["symbol"])
        self.assertEqual(100.5, payload["account"]["equity"])
        self.assertEqual(1, payload["open_positions"])

    def test_okx_check_returns_error_when_credentials_are_missing(self):
        output = io.StringIO()
        env = {
            "OKX_API_KEY": "",
            "OKX_API_SECRET": "",
            "OKX_API_PASSPHRASE": "",
        }

        with patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(output):
            code = main(["--okx-check"])

        self.assertEqual(2, code)
        payload = json.loads(output.getvalue())
        self.assertIn("OKX_API_KEY", payload["error"])

    def test_okx_check_returns_json_error_when_exchange_fails(self):
        fake_exchange = MagicMock()
        fake_exchange.get_account_balance.side_effect = ExchangeError("OKX error 500: unavailable")
        env = {
            "OKX_API_KEY": "key",
            "OKX_API_SECRET": "secret",
            "OKX_API_PASSPHRASE": "passphrase",
        }
        output = io.StringIO()

        with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
            with contextlib.redirect_stdout(output):
                code = main(["--okx-check"])

        self.assertEqual(1, code)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["okx_check"])
        self.assertIn("unavailable", payload["error"])

    def test_okx_smoke_order_requires_explicit_confirmation(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output), patch("runner.OKXExchange") as cls:
            code = main(["--okx-smoke-order"])

        self.assertEqual(2, code)
        cls.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertIn("--confirm-okx-smoke-order", payload["error"])

    def test_okx_smoke_order_rejects_when_risk_check_fails(self):
        fake_exchange = MagicMock()
        fake_exchange.get_account_balance.return_value.equity = 10.0
        fake_exchange.get_positions.return_value = []
        env = {
            "OKX_API_KEY": "key",
            "OKX_API_SECRET": "secret",
            "OKX_API_PASSPHRASE": "passphrase",
        }
        output = io.StringIO()

        with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
            with contextlib.redirect_stdout(output):
                code = main([
                    "--okx-smoke-order",
                    "--confirm-okx-smoke-order",
                    "--okx-smoke-notional",
                    "100",
                    "--okx-smoke-margin",
                    "1",
                ])

        self.assertEqual(2, code)
        fake_exchange.place_order.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["okx_smoke_order"])
        self.assertIn("single position", payload["reason"])

    def test_okx_smoke_order_places_and_cancels_limit_order(self):
        fake_exchange = MagicMock()
        fake_exchange.get_account_balance.return_value.equity = 1000.0
        fake_exchange.get_positions.return_value = []
        fake_exchange.place_order.return_value = OrderResult(
            order_id="okx-1",
            symbol="BTC-USDT-SWAP",
            direction="long",
            qty=0.01,
            status="live",
        )
        fake_exchange.cancel_order.return_value = {"code": "0", "data": [{"ordId": "okx-1"}]}
        env = {
            "OKX_API_KEY": "key",
            "OKX_API_SECRET": "secret",
            "OKX_API_PASSPHRASE": "passphrase",
        }
        output = io.StringIO()

        with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange) as cls:
            with contextlib.redirect_stdout(output):
                code = main([
                    "--okx-smoke-order",
                    "--confirm-okx-smoke-order",
                    "--okx-symbol",
                    "BTC-USDT-SWAP",
                    "--okx-smoke-direction",
                    "long",
                    "--okx-smoke-qty",
                    "0.01",
                    "--okx-smoke-price",
                    "50000",
                    "--okx-smoke-notional",
                    "10",
                    "--okx-smoke-margin",
                    "1",
                ])

        self.assertEqual(0, code)
        cls.assert_called_once_with("key", "secret", "passphrase", sandbox=True)
        fake_exchange.place_order.assert_called_once_with(
            "BTC-USDT-SWAP",
            "long",
            0.01,
            order_type="limit",
            price=50000.0,
        )
        fake_exchange.cancel_order.assert_called_once_with("BTC-USDT-SWAP", "okx-1")
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["okx_smoke_order"])
        self.assertEqual("okx-1", payload["order_id"])
        self.assertTrue(payload["cancel_requested"])

    def test_okx_submit_signal_requires_explicit_confirmation(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output), patch("runner.OKXExchange") as cls:
            code = main(["--okx-submit-signal"])

        self.assertEqual(2, code)
        cls.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertIn("--confirm-okx-submit-signal", payload["error"])

    def test_okx_submit_signal_rejects_when_reconcile_is_inconsistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.save_position("ETH-USDT-SWAP", "long", 100.0, 0.1, 10.0, 1.0, 10.0)
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_positions.return_value = []
            fake_exchange.get_account_balance.return_value.equity = 1000.0
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
                with contextlib.redirect_stdout(output):
                    code = main([
                        "--okx-submit-signal",
                        "--confirm-okx-submit-signal",
                        "--db",
                        str(db_path),
                    ])

            self.assertEqual(2, code)
            fake_exchange.place_order.assert_not_called()
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["okx_submit_signal"])
            self.assertFalse(payload["sync_consistent"])

    def test_okx_submit_signal_places_risk_approved_order_and_records_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            fake_exchange = MagicMock()
            fake_exchange.get_positions.return_value = []
            fake_exchange.get_account_balance.return_value.equity = 1000.0
            fake_exchange.place_order.return_value = OrderResult(
                order_id="okx-live-1",
                symbol="BTC-USDT-SWAP",
                direction="long",
                qty=0.01,
                status="live",
                reason="accepted",
            )
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange) as cls:
                with contextlib.redirect_stdout(output):
                    code = main([
                        "--okx-submit-signal",
                        "--confirm-okx-submit-signal",
                        "--db",
                        str(db_path),
                        "--okx-symbol",
                        "BTC-USDT-SWAP",
                        "--okx-signal-direction",
                        "long",
                        "--okx-signal-price",
                        "50000",
                        "--okx-signal-notional",
                        "10",
                        "--okx-signal-margin",
                        "1",
                        "--okx-signal-leverage",
                        "10",
                    ])

            self.assertEqual(0, code)
            cls.assert_called_once_with("key", "secret", "passphrase", sandbox=True)
            fake_exchange.place_order.assert_called_once_with(
                "BTC-USDT-SWAP",
                "long",
                0.0002,
                order_type="market",
                price=50000.0,
                fee=0.0005,
            )
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["okx_submit_signal"])
            self.assertTrue(payload["accepted"])
            self.assertEqual("live", payload["status"])
            self.assertIsNotNone(payload["order_id"])
            self.assertEqual("okx-live-1", payload["exchange_order_id"])
            db = StateDB(db_path)
            try:
                orders = db.get_order(payload["order_id"])
                self.assertEqual("live", orders["status"])
                self.assertEqual("okx-live-1", orders["exchange_order_id"])
                self.assertEqual([], db.get_open_positions())
            finally:
                db.close()

    def test_okx_sync_orders_returns_error_when_credentials_are_missing(self):
        output = io.StringIO()
        env = {
            "OKX_API_KEY": "",
            "OKX_API_SECRET": "",
            "OKX_API_PASSPHRASE": "",
        }

        with patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(output):
            code = main(["--okx-sync-orders"])

        self.assertEqual(2, code)
        payload = json.loads(output.getvalue())
        self.assertIn("OKX_API_KEY", payload["error"])

    def test_okx_sync_orders_updates_live_order_to_filled_and_opens_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                order_id = db.save_order(
                    "BTC-USDT-SWAP",
                    "long",
                    0.0002,
                    price=50000.0,
                    meta={"notional": 10.0, "margin": 1.0, "leverage": 10.0},
                )
                db.update_order_status(order_id, "live", exchange_order_id="okx-live-1")
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_order_status.return_value = {
                "code": "0",
                "data": [
                    {
                        "ordId": "okx-live-1",
                        "state": "filled",
                        "avgPx": "50010",
                        "accFillSz": "0.0002",
                        "fee": "0.0005",
                    }
                ],
            }
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange) as cls:
                with contextlib.redirect_stdout(output):
                    code = main(["--okx-sync-orders", "--db", str(db_path)])

            self.assertEqual(0, code)
            cls.assert_called_once_with("key", "secret", "passphrase", sandbox=True)
            fake_exchange.get_order_status.assert_called_once_with("BTC-USDT-SWAP", "okx-live-1")
            payload = json.loads(output.getvalue())
            self.assertEqual(1, payload["checked_orders"])
            self.assertEqual(1, payload["filled_orders"])
            self.assertEqual(1, payload["opened_positions"])
            db = StateDB(db_path)
            try:
                order = db.get_order(order_id)
                self.assertEqual("filled", order["status"])
                self.assertEqual(50010.0, order["fill_price"])
                positions = db.get_open_positions()
                self.assertEqual(1, len(positions))
                self.assertEqual("BTC-USDT-SWAP", positions[0]["symbol"])
                self.assertEqual("long", positions[0]["direction"])
                self.assertEqual(10.0, positions[0]["notional"])
                self.assertEqual(1.0, positions[0]["margin"])
            finally:
                db.close()

    def test_okx_sync_orders_keeps_live_order_without_opening_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                order_id = db.save_order(
                    "BTC-USDT-SWAP",
                    "long",
                    0.0002,
                    price=50000.0,
                    meta={"notional": 10.0, "margin": 1.0, "leverage": 10.0},
                )
                db.update_order_status(order_id, "live", exchange_order_id="okx-live-1")
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_order_status.return_value = {
                "code": "0",
                "data": [{"ordId": "okx-live-1", "state": "live"}],
            }
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
                with contextlib.redirect_stdout(output):
                    code = main(["--okx-sync-orders", "--db", str(db_path)])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertEqual(1, payload["checked_orders"])
            self.assertEqual(0, payload["filled_orders"])
            db = StateDB(db_path)
            try:
                order = db.get_order(order_id)
                self.assertEqual("live", order["status"])
                self.assertEqual([], db.get_open_positions())
            finally:
                db.close()

    def test_okx_close_position_requires_explicit_confirmation(self):
        output = io.StringIO()

        with contextlib.redirect_stdout(output), patch("runner.OKXExchange") as cls:
            code = main(["--okx-close-position", "--position-id", "pos-1"])

        self.assertEqual(2, code)
        cls.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertIn("--confirm-okx-close-position", payload["error"])

    def test_okx_close_position_places_opposite_order_and_records_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                position_id = db.save_position(
                    "BTC-USDT-SWAP",
                    "long",
                    entry_price=50000.0,
                    qty=0.0002,
                    notional=10.0,
                    margin=1.0,
                    leverage=10.0,
                )
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_positions.return_value = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]
            fake_exchange.place_order.return_value = OrderResult(
                order_id="okx-close-1",
                symbol="BTC-USDT-SWAP",
                direction="short",
                qty=0.0002,
                status="live",
            )
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
                with contextlib.redirect_stdout(output):
                    code = main([
                        "--okx-close-position",
                        "--confirm-okx-close-position",
                        "--db",
                        str(db_path),
                        "--position-id",
                        position_id,
                        "--okx-close-price",
                        "50100",
                    ])

            self.assertEqual(0, code)
            fake_exchange.place_order.assert_called_once_with(
                "BTC-USDT-SWAP",
                "short",
                0.0002,
                order_type="market",
                price=50100.0,
                fee=0.0005,
            )
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["okx_close_position"])
            self.assertEqual(position_id, payload["position_id"])
            self.assertIsNotNone(payload["order_id"])
            self.assertEqual("okx-close-1", payload["exchange_order_id"])
            db = StateDB(db_path)
            try:
                order = db.get_order(payload["order_id"])
                self.assertEqual("live", order["status"])
                self.assertEqual("close", json.loads(order["meta"])["action"])
                self.assertEqual(position_id, json.loads(order["meta"])["position_id"])
            finally:
                db.close()

    def test_okx_sync_orders_closes_position_and_records_trade_for_filled_close_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                position_id = db.save_position(
                    "BTC-USDT-SWAP",
                    "long",
                    entry_price=50000.0,
                    qty=0.0002,
                    notional=10.0,
                    margin=1.0,
                    leverage=10.0,
                )
                order_id = db.save_order(
                    "BTC-USDT-SWAP",
                    "short",
                    0.0002,
                    price=50100.0,
                    meta={
                        "action": "close",
                        "position_id": position_id,
                        "exit_reason": "manual_okx_close",
                    },
                )
                db.update_order_status(order_id, "live", exchange_order_id="okx-close-1")
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_order_status.return_value = {
                "code": "0",
                "data": [
                    {
                        "ordId": "okx-close-1",
                        "state": "filled",
                        "avgPx": "50100",
                        "accFillSz": "0.0002",
                        "fee": "0.0005",
                    }
                ],
            }
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
                with contextlib.redirect_stdout(output):
                    code = main(["--okx-sync-orders", "--db", str(db_path)])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertEqual(1, payload["closed_positions"])
            self.assertEqual(1, payload["saved_trades"])
            db = StateDB(db_path)
            try:
                self.assertEqual([], db.get_open_positions())
                trades = db.get_recent_trades()
                self.assertEqual(1, len(trades))
                self.assertEqual("manual_okx_close", trades[0]["exit_reason"])
                self.assertGreater(trades[0]["pnl"], 0)
            finally:
                db.close()

    def test_okx_snapshot_returns_error_when_credentials_are_missing(self):
        output = io.StringIO()
        env = {
            "OKX_API_KEY": "",
            "OKX_API_SECRET": "",
            "OKX_API_PASSPHRASE": "",
        }

        with patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(output):
            code = main(["--okx-snapshot"])

        self.assertEqual(2, code)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["okx_snapshot"])
        self.assertIn("OKX_API_KEY", payload["error"])

    def test_okx_snapshot_writes_account_snapshot_and_outputs_runtime_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.save_position("BTC-USDT-SWAP", "long", 50000.0, 0.0002, 10.0, 1.0, 10.0)
                order_id = db.save_order("BTC-USDT-SWAP", "long", 0.0002, price=50000.0)
                db.update_order_status(order_id, "live", exchange_order_id="okx-live-1")
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_account_balance.return_value.equity = 1000.0
            fake_exchange.get_account_balance.return_value.available_margin = 990.0
            fake_exchange.get_account_balance.return_value.used_margin = 10.0
            fake_exchange.get_positions.return_value = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
                with contextlib.redirect_stdout(output):
                    code = main(["--okx-snapshot", "--db", str(db_path)])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["okx_snapshot"])
            self.assertEqual(1000.0, payload["account"]["equity"])
            self.assertEqual(1, payload["local_open_positions"])
            self.assertEqual(1, payload["exchange_open_positions"])
            self.assertEqual(1, payload["pending_orders"])
            db = StateDB(db_path)
            try:
                history = db.get_account_history()
                self.assertEqual(1, len(history))
                self.assertEqual(1000.0, history[0]["equity"])
                risk_status = json.loads(history[0]["risk_status"])
                self.assertEqual("okx_snapshot", risk_status["source"])
                self.assertEqual(1, risk_status["pending_orders"])
            finally:
                db.close()

    def test_okx_monitor_loop_returns_error_when_credentials_are_missing(self):
        output = io.StringIO()
        env = {
            "OKX_API_KEY": "",
            "OKX_API_SECRET": "",
            "OKX_API_PASSPHRASE": "",
        }

        with patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(output):
            code = main(["--okx-monitor-loop"])

        self.assertEqual(2, code)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["okx_monitor_loop"])
        self.assertIn("OKX_API_KEY", payload["error"])

    def test_okx_monitor_loop_syncs_orders_and_writes_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                order_id = db.save_order(
                    "BTC-USDT-SWAP",
                    "long",
                    0.0002,
                    price=50000.0,
                    meta={"notional": 10.0, "margin": 1.0, "leverage": 10.0},
                )
                db.update_order_status(order_id, "live", exchange_order_id="okx-live-1")
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_order_status.return_value = {
                "code": "0",
                "data": [
                    {
                        "ordId": "okx-live-1",
                        "state": "filled",
                        "avgPx": "50010",
                        "accFillSz": "0.0002",
                        "fee": "0.0005",
                    }
                ],
            }
            fake_exchange.get_account_balance.return_value.equity = 1000.0
            fake_exchange.get_account_balance.return_value.available_margin = 990.0
            fake_exchange.get_account_balance.return_value.used_margin = 10.0
            fake_exchange.get_positions.return_value = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
                with contextlib.redirect_stdout(output):
                    code = main([
                        "--okx-monitor-loop",
                        "--iterations",
                        "2",
                        "--interval",
                        "0",
                        "--db",
                        str(db_path),
                    ])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["okx_monitor_loop"])
            self.assertEqual(2, payload["iterations"])
            self.assertEqual(2, len(payload["cycles"]))
            self.assertEqual(1, payload["cycles"][0]["sync"]["filled_orders"])
            self.assertEqual(1, payload["cycles"][0]["snapshot"]["local_open_positions"])
            db = StateDB(db_path)
            try:
                self.assertEqual(2, len(db.get_account_history()))
                self.assertEqual(1, len(db.get_open_positions()))
            finally:
                db.close()

    def test_okx_health_report_outputs_ok_when_local_and_exchange_state_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.save_position("BTC-USDT-SWAP", "long", 50000.0, 0.0002, 10.0, 1.0, 10.0)
            finally:
                db.close()
            fake_exchange = MagicMock()
            fake_exchange.get_positions.return_value = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]
            env = {
                "OKX_API_KEY": "key",
                "OKX_API_SECRET": "secret",
                "OKX_API_PASSPHRASE": "passphrase",
            }
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
                with contextlib.redirect_stdout(output):
                    code = main(["--okx-health-report", "--db", str(db_path)])

            self.assertEqual(0, code)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["okx_health_report"])
            self.assertEqual("ok", payload["status"])
            self.assertEqual([], payload["issues"])
            self.assertEqual(1, payload["local_open_positions"])
            self.assertEqual(1, payload["exchange_open_positions"])
            self.assertGreater(payload["health_report_id"], 0)
            self.assertEqual(0, payload["alerts_saved"])

    def test_okx_health_report_returns_critical_when_exchange_fails(self):
        fake_exchange = MagicMock()
        fake_exchange.get_positions.side_effect = ExchangeError("OKX error 500: unavailable")
        env = {
            "OKX_API_KEY": "key",
            "OKX_API_SECRET": "secret",
            "OKX_API_PASSPHRASE": "passphrase",
        }
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            output = io.StringIO()

            with patch.dict(os.environ, env, clear=False), patch("runner.OKXExchange", return_value=fake_exchange):
                with contextlib.redirect_stdout(output):
                    code = main(["--okx-health-report", "--db", str(db_path)])

            self.assertEqual(1, code)
            payload = json.loads(output.getvalue())
            self.assertTrue(payload["okx_health_report"])
            self.assertEqual("critical", payload["status"])
            self.assertEqual("api_failure", payload["issues"][0]["kind"])
            self.assertIn("unavailable", payload["issues"][0]["message"])
            self.assertGreater(payload["health_report_id"], 0)
            self.assertEqual(1, payload["alerts_saved"])
            db = StateDB(db_path)
            try:
                alerts = db.get_recent_health_alerts()
                self.assertEqual(1, len(alerts))
                self.assertEqual("api_failure", alerts[0]["kind"])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
