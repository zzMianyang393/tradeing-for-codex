from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from config import BacktestConfig
from exchange import DryRunExchange, OrderResult
from executor import ExecutionRequest, Executor
from risk_manager import RiskManager
from state_db import StateDB
from strategy import Signal


def _bars(atr_pct: float = 0.02):
    bar = MagicMock()
    bar.atr_pct = atr_pct
    bar.close = 100.0
    return [bar]


class TestExecutor(unittest.TestCase):
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

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()

    def test_execute_signal_records_filled_order_and_open_position(self):
        signal = Signal("BTC-USDT-SWAP", 1, 3.5, "range", "range_revert_long")
        request = ExecutionRequest.from_signal(
            signal=signal,
            price=100.0,
            notional=10.0,
            margin=1.0,
            leverage=10.0,
        )

        result = self.executor.execute_signal(request, equity=100.0, current_step=1, bars=_bars(), idx=0)

        self.assertTrue(result.accepted)
        self.assertEqual("filled", result.status)
        self.assertIsNotNone(result.order_id)
        self.assertIsNotNone(result.position_id)
        order = self.db.get_order(result.order_id)
        self.assertEqual("filled", order["status"])
        self.assertEqual("long", order["direction"])
        positions = self.db.get_open_positions()
        self.assertEqual(1, len(positions))
        self.assertEqual("BTC-USDT-SWAP", positions[0]["symbol"])
        self.assertAlmostEqual(1.0, self.risk_manager.get_status().total_margin_used)

    def test_rejected_signal_records_risk_event_without_order(self):
        signal = Signal("BTC-USDT-SWAP", 1, 3.5, "range", "range_revert_long")
        request = ExecutionRequest.from_signal(
            signal=signal,
            price=100.0,
            notional=100.0,
            margin=50.0,
            leverage=2.0,
        )

        result = self.executor.execute_signal(request, equity=10.0, current_step=1, bars=_bars(), idx=0)

        self.assertFalse(result.accepted)
        self.assertIn("single position", result.reason)
        self.assertIsNone(result.order_id)
        self.assertEqual([], self.db.get_open_positions())
        events = self.db.get_risk_events()
        self.assertEqual(1, len(events))
        self.assertEqual("reject", events[0]["event_type"])

    def test_execute_signal_accepts_live_order_without_opening_position(self):
        live_exchange = MagicMock()
        live_exchange.place_order.return_value = OrderResult(
            order_id="okx-1",
            symbol="BTC-USDT-SWAP",
            direction="long",
            qty=0.1,
            status="live",
            reason="accepted",
        )
        executor = Executor(live_exchange, self.risk_manager, self.db, self.config)
        signal = Signal("BTC-USDT-SWAP", 1, 3.5, "range", "range_revert_long")
        request = ExecutionRequest.from_signal(
            signal=signal,
            price=100.0,
            notional=10.0,
            margin=1.0,
            leverage=10.0,
        )

        result = executor.execute_signal(request, equity=100.0, current_step=1, bars=_bars(), idx=0)

        self.assertTrue(result.accepted)
        self.assertEqual("live", result.status)
        self.assertIsNotNone(result.order_id)
        self.assertIsNone(result.position_id)
        order = self.db.get_order(result.order_id)
        self.assertEqual("live", order["status"])
        self.assertEqual("okx-1", order["exchange_order_id"])
        self.assertEqual([], self.db.get_open_positions())

    def test_sync_state_consistent_keeps_risk_manager_running(self):
        self.db.save_position("BTC-USDT-SWAP", "long", 100.0, 0.1, 10.0, 1.0, 10.0)
        self.exchange.positions = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]

        result = self.executor.sync_state(current_step=10)

        self.assertTrue(result.consistent)
        self.assertFalse(self.risk_manager.get_status().is_paused)
        self.assertEqual([], self.db.get_risk_events())

    def test_sync_state_inconsistency_records_event_and_pauses(self):
        self.db.save_position("BTC-USDT-SWAP", "long", 100.0, 0.1, 10.0, 1.0, 10.0)
        self.exchange.positions = [{"symbol": "ETH-USDT-SWAP", "direction": "short"}]

        result = self.executor.sync_state(current_step=10)

        self.assertFalse(result.consistent)
        status = self.risk_manager.get_status()
        self.assertTrue(status.is_paused)
        self.assertEqual("position_inconsistency", status.pause_reason)
        events = self.db.get_risk_events()
        self.assertEqual(1, len(events))
        self.assertEqual("position_inconsistency", events[0]["event_type"])

    def test_manage_positions_closes_long_take_profit_and_records_trade(self):
        position_id = self.db.save_position(
            "BTC-USDT-SWAP",
            "long",
            entry_price=100.0,
            qty=0.1,
            notional=10.0,
            margin=1.0,
            leverage=10.0,
            stop_loss=95.0,
            take_profit=105.0,
        )
        self.exchange.positions = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]
        self.risk_manager._track_open("BTC-USDT-SWAP", 1.0)

        actions = self.executor.manage_positions({"BTC-USDT-SWAP": 106.0}, current_step=20)

        self.assertEqual(1, len(actions))
        self.assertEqual(position_id, actions[0].position_id)
        self.assertEqual("take_profit", actions[0].reason)
        self.assertEqual([], self.db.get_open_positions())
        trades = self.db.get_recent_trades()
        self.assertEqual(1, len(trades))
        self.assertEqual("BTC-USDT-SWAP", trades[0]["symbol"])
        self.assertEqual("take_profit", trades[0]["exit_reason"])
        self.assertGreater(trades[0]["pnl"], 0)
        self.assertAlmostEqual(0.0, self.risk_manager.get_status().total_margin_used)
        self.assertEqual([], self.exchange.get_positions())

    def test_manage_positions_keeps_position_when_no_exit_triggered(self):
        self.db.save_position(
            "BTC-USDT-SWAP",
            "long",
            entry_price=100.0,
            qty=0.1,
            notional=10.0,
            margin=1.0,
            leverage=10.0,
            stop_loss=95.0,
            take_profit=105.0,
        )
        self.exchange.positions = [{"symbol": "BTC-USDT-SWAP", "direction": "long"}]

        actions = self.executor.manage_positions({"BTC-USDT-SWAP": 102.0}, current_step=20)

        self.assertEqual([], actions)
        self.assertEqual(1, len(self.db.get_open_positions()))
        self.assertEqual(0, self.db.count_trades())

    def test_manage_positions_closes_short_stop_loss(self):
        self.db.save_position(
            "ETH-USDT-SWAP",
            "short",
            entry_price=100.0,
            qty=0.1,
            notional=10.0,
            margin=1.0,
            leverage=10.0,
            stop_loss=105.0,
            take_profit=95.0,
        )
        self.exchange.positions = [{"symbol": "ETH-USDT-SWAP", "direction": "short"}]

        actions = self.executor.manage_positions({"ETH-USDT-SWAP": 106.0}, current_step=20)

        self.assertEqual(1, len(actions))
        self.assertEqual("stop_or_trail", actions[0].reason)
        trades = self.db.get_recent_trades()
        self.assertEqual(1, len(trades))
        self.assertEqual("short", trades[0]["direction"])
        self.assertEqual("stop_or_trail", trades[0]["exit_reason"])
        self.assertLess(trades[0]["pnl"], 0)


if __name__ == "__main__":
    unittest.main()
