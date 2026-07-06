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
from exchange import DryRunExchange
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


if __name__ == "__main__":
    unittest.main()
