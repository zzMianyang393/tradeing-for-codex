from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from config import BacktestConfig
from exchange import OKXExchange, AccountInfo, PositionInfo, Ticker, OrderResult, OrderStatus, OKXAPIError
from executor import Executor, ExecutionResult, SyncResult
from risk_manager import RiskManager
from state_db import StateDB


def _make_bar(atr_pct=0.02, close=50000.0):
    """Create a mock bar with attribute access (not dict)."""
    bar = MagicMock()
    bar.ts = 1
    bar.close = close
    bar.atr_pct = atr_pct
    return bar


def _make_signal(symbol="BTC-USDT-SWAP", direction=1, score=3.5, reason="range_revert_long"):
    sig = MagicMock()
    sig.symbol = symbol
    sig.direction = direction
    sig.score = score
    sig.regime = "range"
    sig.reason = reason
    return sig


# ---------------------------------------------------------------------------
# Exchange tests
# ---------------------------------------------------------------------------

class TestExchangeDataclasses(unittest.TestCase):
    def test_account_info_defaults(self):
        info = AccountInfo()
        self.assertEqual(info.total_equity, 0.0)
        self.assertEqual(info.currency, "USDT")

    def test_position_info_defaults(self):
        pos = PositionInfo()
        self.assertEqual(pos.symbol, "")
        self.assertEqual(pos.direction, "")

    def test_ticker_defaults(self):
        t = Ticker()
        self.assertEqual(t.symbol, "")

    def test_order_result_defaults(self):
        r = OrderResult()
        self.assertFalse(r.success)

    def test_order_status_defaults(self):
        s = OrderStatus()
        self.assertEqual(s.status, "")


class TestOKXExchange(unittest.TestCase):
    def test_init(self):
        ex = OKXExchange("key", "secret", "pass", sandbox=True)
        self.assertEqual(ex.api_key, "key")
        self.assertTrue(ex.sandbox)

    def test_sign(self):
        ex = OKXExchange("key", "secret", "pass")
        sig = ex._sign("2026-01-01T00:00:00.000Z", "GET", "/api/v5/account/balance")
        self.assertIsInstance(sig, str)
        self.assertTrue(len(sig) > 0)

    def test_okx_api_error(self):
        err = OKXAPIError("50001", "error msg")
        self.assertEqual(err.code, "50001")
        self.assertEqual(err.message, "error msg")
        self.assertIn("50001", str(err))


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------

class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.config = BacktestConfig(
            rm_enabled=True,
            rm_max_single_position_pct=1.0,  # Allow large positions for testing
            rm_max_total_position_pct=1.0,
            risk_per_trade=0.05,
        )
        self.exchange = MagicMock(spec=OKXExchange)
        self.risk_manager = RiskManager(self.config)
        self.state_db = MagicMock(spec=StateDB)

        self.executor = Executor(
            exchange=self.exchange,
            risk_manager=self.risk_manager,
            state_db=self.state_db,
            config=self.config,
            dry_run=False,
        )

    def test_execute_signal_risk_rejected(self):
        """Signal rejected by risk manager."""
        self.exchange.get_ticker.return_value = Ticker(last=50000.0)
        self.exchange.get_account_balance.return_value = AccountInfo(total_equity=10.0)

        # Set up risk manager to reject
        self.risk_manager._is_paused = True
        self.risk_manager._pause_until_step = 999

        bars = [_make_bar()]
        result = self.executor.execute_signal(_make_signal(), bars, 0)

        self.assertFalse(result.success)
        self.assertIn("Risk rejected", result.error)

    def test_execute_signal_dry_run(self):
        """Dry run mode doesn't place orders."""
        self.executor.dry_run = True
        self.exchange.get_ticker.return_value = Ticker(last=50000.0)
        self.exchange.get_account_balance.return_value = AccountInfo(total_equity=10.0)

        bars = [_make_bar()]
        result = self.executor.execute_signal(_make_signal(), bars, 0)

        self.assertTrue(result.success)
        self.exchange.place_order.assert_not_called()

    def test_execute_signal_success(self):
        """Successful order placement."""
        self.exchange.get_ticker.return_value = Ticker(last=50000.0)
        self.exchange.get_account_balance.return_value = AccountInfo(total_equity=10.0)
        self.exchange.place_order.return_value = OrderResult(success=True, order_id="123")

        bars = [_make_bar()]
        result = self.executor.execute_signal(_make_signal(), bars, 0)

        self.assertTrue(result.success)
        self.assertEqual(result.order_id, "123")
        self.state_db.save_order.assert_called_once()

    def test_sync_state_consistent(self):
        """Sync when positions match."""
        self.exchange.get_positions.return_value = []
        self.state_db.reconcile_positions.return_value = MagicMock(
            consistent=True, local_only=[], exchange_only=[]
        )

        result = self.executor.sync_state()
        self.assertTrue(result.consistent)

    def test_sync_state_inconsistent(self):
        """Sync when positions don't match."""
        self.exchange.get_positions.return_value = []
        self.state_db.reconcile_positions.return_value = MagicMock(
            consistent=False, local_only=[{"symbol": "BTC"}], exchange_only=[]
        )

        result = self.executor.sync_state()
        self.assertFalse(result.consistent)
        self.assertEqual(result.local_only_count, 1)
        self.assertTrue(self.risk_manager._is_paused)


# ---------------------------------------------------------------------------
# Runner tests
# ---------------------------------------------------------------------------

class TestRunReport(unittest.TestCase):
    def test_defaults(self):
        from runner import RunReport
        report = RunReport()
        self.assertEqual(report.equity, 0.0)
        self.assertEqual(report.signals_generated, 0)


class TestCreateRunner(unittest.TestCase):
    def test_create_runner(self):
        from runner import create_runner
        config = BacktestConfig(rm_enabled=True)

        with patch("runner.OKXExchange") as mock_ex:
            mock_ex.return_value = MagicMock()
            runner = create_runner(
                config=config,
                api_key="test",
                secret="test",
                passphrase="test",
                sandbox=True,
                dry_run=True,
                symbols=["BTC-USDT-SWAP"],
            )
            self.assertIsNotNone(runner)
            self.assertTrue(runner.dry_run)
            self.assertEqual(runner.symbols, ["BTC-USDT-SWAP"])


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestCLIRunner(unittest.TestCase):
    def test_imports(self):
        """cli_runner module imports without error."""
        import cli_runner
        self.assertTrue(hasattr(cli_runner, "main"))
        self.assertTrue(hasattr(cli_runner, "cmd_status"))
        self.assertTrue(hasattr(cli_runner, "cmd_once"))


# ---------------------------------------------------------------------------
# Integration: risk_manager + executor
# ---------------------------------------------------------------------------

class TestRiskExecutorIntegration(unittest.TestCase):
    def test_risk_blocks_order_in_executor(self):
        """Verify risk manager properly blocks orders in executor."""
        config = BacktestConfig(
            rm_enabled=True,
            rm_max_single_position_pct=0.40,
            rm_consecutive_loss_pause=3,
            risk_per_trade=0.05,
        )
        exchange = MagicMock(spec=OKXExchange)
        risk_manager = RiskManager(config)
        state_db = MagicMock(spec=StateDB)

        executor = Executor(
            exchange=exchange,
            risk_manager=risk_manager,
            state_db=state_db,
            config=config,
        )

        # Set up consecutive losses to trigger pause
        risk_manager._consecutive_losses = 3

        exchange.get_ticker.return_value = Ticker(last=100.0)
        exchange.get_account_balance.return_value = AccountInfo(total_equity=10.0)

        bars = [_make_bar(close=100.0)]
        result = executor.execute_signal(_make_signal(), bars, 0)

        self.assertFalse(result.success)
        self.assertIn("Risk rejected", result.error)
        exchange.place_order.assert_not_called()

    def test_risk_pause_tracks_positions(self):
        """Verify risk manager tracks position opens/closes."""
        config = BacktestConfig(rm_enabled=True)
        risk_manager = RiskManager(config)

        risk_manager._track_open("BTC-USDT-SWAP", 5.0)
        risk_manager._track_open("ETH-USDT-SWAP", 3.0)
        self.assertAlmostEqual(risk_manager._total_margin_used, 8.0)

        risk_manager.on_trade_close(1.0, 10, "BTC-USDT-SWAP", 5.0)
        self.assertAlmostEqual(risk_manager._total_margin_used, 3.0)


if __name__ == "__main__":
    unittest.main()
