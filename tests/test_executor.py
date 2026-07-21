from __future__ import annotations

import tempfile
import unittest
import sqlite3
from datetime import datetime, timezone
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

    def test_poll_order_fill_returns_terminal_order_state(self):
        live_exchange = MagicMock()
        live_exchange.get_order_status.side_effect = [
            {"data": [{"state": "live", "ordId": "okx-1"}]},
            {"data": [{"state": "filled", "ordId": "okx-1", "avgPx": "100"}]},
        ]
        executor = Executor(live_exchange, self.risk_manager, self.db, self.config)

        result = executor.poll_order_fill(
            "BTC-USDT-SWAP",
            "okx-1",
            max_wait_seconds=1.0,
            poll_interval=0.0,
        )

        self.assertEqual("filled", result["state"])
        self.assertEqual(2, live_exchange.get_order_status.call_count)

    def test_cancel_stale_orders_cancels_old_active_exchange_orders(self):
        live_exchange = MagicMock()
        live_exchange.cancel_order.return_value = {"code": "0"}
        executor = Executor(live_exchange, self.risk_manager, self.db, self.config)
        order_id = self.db.save_order("BTC-USDT-SWAP", "long", 0.01, price=100.0)
        self.db.update_order_status(order_id, "live", exchange_order_id="okx-1")
        conn = sqlite3.connect(str(Path(self._tmp.name) / "state.db"))
        try:
            conn.execute("UPDATE orders SET created_at='2000-01-01 00:00:00' WHERE id=?", (order_id,))
            conn.commit()
        finally:
            conn.close()

        cancelled = executor.cancel_stale_orders(max_age_minutes=1.0)

        self.assertEqual(["okx-1"], cancelled)
        live_exchange.cancel_order.assert_called_once_with("BTC-USDT-SWAP", "okx-1")
        self.assertEqual("cancelled", self.db.get_order(order_id)["status"])

    def test_cancel_stale_orders_treats_naive_created_at_as_utc(self):
        live_exchange = MagicMock()
        executor = Executor(live_exchange, self.risk_manager, self.db, self.config)
        order_id = self.db.save_order("BTC-USDT-SWAP", "long", 0.01, price=100.0)
        self.db.update_order_status(order_id, "live", exchange_order_id="okx-1")
        conn = sqlite3.connect(str(Path(self._tmp.name) / "state.db"))
        try:
            conn.execute(
                "UPDATE orders SET created_at=? WHERE id=?",
                (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), order_id),
            )
            conn.commit()
        finally:
            conn.close()

        cancelled = executor.cancel_stale_orders(max_age_minutes=30.0)

        self.assertEqual([], cancelled)
        live_exchange.cancel_order.assert_not_called()

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


    def test_execute_pairs_signal_success(self):
        live_exchange = MagicMock()
        live_exchange.place_order.side_effect = [
            OrderResult(order_id="okx-a", symbol="FIL-USDT-SWAP", direction="long", qty=5.0, status="filled", fill_price=10.0, fill_qty=5.0, success=True),
            OrderResult(order_id="okx-b", symbol="OP-USDT-SWAP", direction="short", qty=25.0, status="filled", fill_price=2.0, fill_qty=25.0, success=True),
        ]
        
        executor = Executor(live_exchange, self.risk_manager, self.db, self.config)
        
        result = executor.execute_pairs_signal(
            pair_key="FIL-OP",
            symbol_a="FIL-USDT-SWAP",
            symbol_b="OP-USDT-SWAP",
            direction_a=1,
            direction_b=-1,
            notional_a=50.0,
            notional_b=50.0,
            margin=10.0,
            leverage=10.0,
            entry_z=2.1,
            beta=1.2,
            alpha=0.1,
            price_a=10.0,
            price_b=2.0,
        )
        
        self.assertTrue(result.accepted)
        self.assertEqual("filled", result.status)
        order_ids = result.order_id.split(",")
        order_a = self.db.get_order(order_ids[0])
        order_b = self.db.get_order(order_ids[1])
        self.assertEqual("okx-a", order_a["exchange_order_id"])
        self.assertEqual("okx-b", order_b["exchange_order_id"])
        
        open_pos = self.db.get_open_pairs_positions()
        self.assertEqual(1, len(open_pos))
        self.assertEqual("FIL-OP", open_pos[0]["pair_key"])

    def test_execute_pairs_signal_leg_lock(self):
        live_exchange = MagicMock()
        # Leg A succeeds, Leg B fails
        live_exchange.place_order.side_effect = [
            OrderResult(order_id="okx-a", symbol="FIL-USDT-SWAP", direction="long", qty=5.0, status="filled", fill_price=10.0, fill_qty=5.0, success=True),
            Exception("Exchange down"),
            # Reversal order for Leg A
            OrderResult(order_id="okx-rev", symbol="FIL-USDT-SWAP", direction="short", qty=5.0, status="filled", fill_price=10.0, fill_qty=5.0, success=True),
        ]
        
        executor = Executor(live_exchange, self.risk_manager, self.db, self.config)
        
        result = executor.execute_pairs_signal(
            pair_key="FIL-OP",
            symbol_a="FIL-USDT-SWAP",
            symbol_b="OP-USDT-SWAP",
            direction_a=1,
            direction_b=-1,
            notional_a=50.0,
            notional_b=50.0,
            margin=10.0,
            leverage=10.0,
            entry_z=2.1,
            beta=1.2,
            alpha=0.1,
            price_a=10.0,
            price_b=2.0,
        )
        
        self.assertFalse(result.accepted)
        self.assertEqual("failed", result.status)
        self.assertIn("Leg-lock", result.reason)
        # Check that reversing order was placed
        live_exchange.place_order.assert_any_call("FIL-USDT-SWAP", "short", 5.0, order_type="market", price=10.0, fee=0.025)

    def test_manage_pairs_positions_exit(self):
        # Save an open pairs position
        pos_id = self.db.save_pairs_position(
            pair_key="FIL-OP",
            symbol_a="FIL-USDT-SWAP",
            symbol_b="OP-USDT-SWAP",
            direction_a="long",
            direction_b="short",
            entry_price_a=10.0,
            entry_price_b=2.0,
            qty_a=5.0,
            qty_b=25.0,
            notional_a=50.0,
            notional_b=50.0,
            margin=10.0,
            leverage=10.0,
            entry_z=2.1,
            beta=1.2,
            alpha=0.1,
        )
        
        live_exchange = MagicMock()
        live_exchange.close_position.side_effect = [
            OrderResult(order_id="close-a", symbol="FIL-USDT-SWAP", direction="long", qty=5.0, status="filled", fill_price=11.0, fill_qty=5.0, success=True),
            OrderResult(order_id="close-b", symbol="OP-USDT-SWAP", direction="short", qty=25.0, status="filled", fill_price=1.8, fill_qty=25.0, success=True),
        ]
        
        executor = Executor(live_exchange, self.risk_manager, self.db, self.config)
        
        pairs_signals = {
            "FIL-OP": {
                "signal": "exit",
                "zscore": 0.1,
                "price_a": 11.0,
                "price_b": 1.8,
            }
        }
        
        actions = executor.manage_pairs_positions(pairs_signals, {"FIL-USDT-SWAP": 11.0, "OP-USDT-SWAP": 1.8})
        
        self.assertEqual(1, len(actions))
        self.assertEqual("FIL-OP", actions[0].symbol)
        self.assertEqual("mean_reversion", actions[0].reason)
        # PnL: A = (11 - 10)*5 = 5, B = (2 - 1.8)*25 = 5. Total = 10. Fee = (55 + 45)*0.0005 = 0.05. Net = 9.95.
        self.assertAlmostEqual(9.95, actions[0].pnl)
        
        # Verify DB is closed
        open_pos = self.db.get_open_pairs_positions()
        self.assertEqual(0, len(open_pos))
        
        # Verify trade recorded
        cursor = self.db._conn.execute("SELECT * FROM pairs_trades")
        trades = cursor.fetchall()
        self.assertEqual(1, len(trades))
        self.assertEqual(9.95, trades[0]["pnl"])

    def test_manage_pairs_positions_time_stop(self):
        """Positions held longer than pairs_max_hold_bars must be force-closed with reason=time_stop."""
        import sqlite3
        from datetime import datetime, timedelta, timezone

        pos_id = self.db.save_pairs_position(
            pair_key="ARB-AVAX",
            symbol_a="ARB-USDT-SWAP",
            symbol_b="AVAX-USDT-SWAP",
            direction_a="short",
            direction_b="long",
            entry_price_a=1.0,
            entry_price_b=20.0,
            qty_a=100.0,
            qty_b=5.0,
            notional_a=100.0,
            notional_b=100.0,
            margin=20.0,
            leverage=10.0,
            entry_z=2.5,
            beta=0.9,
            alpha=0.05,
        )
        # Backdate opened_at to simulate 201 bars ago (> pairs_max_hold_bars=200)
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=201 * 15)).strftime("%Y-%m-%d %H:%M:%S")
        self.db._conn.execute("UPDATE pairs_positions SET opened_at=? WHERE id=?", (old_time, pos_id))
        self.db._conn.commit()

        live_exchange = MagicMock()
        live_exchange.close_position.side_effect = [
            OrderResult(order_id="close-a", symbol="ARB-USDT-SWAP", direction="short", qty=100.0, status="filled", fill_price=1.0, fill_qty=100.0, success=True),
            OrderResult(order_id="close-b", symbol="AVAX-USDT-SWAP", direction="long", qty=5.0, status="filled", fill_price=20.0, fill_qty=5.0, success=True),
        ]
        executor = Executor(live_exchange, self.risk_manager, self.db, self.config)

        # Signal is "hold" — should still force-exit due to time stop
        pairs_signals = {
            "ARB-AVAX": {
                "signal": "hold",
                "zscore": 1.5,
                "price_a": 1.0,
                "price_b": 20.0,
            }
        }
        actions = executor.manage_pairs_positions(
            pairs_signals, {"ARB-USDT-SWAP": 1.0, "AVAX-USDT-SWAP": 20.0}
        )

        self.assertEqual(1, len(actions))
        self.assertEqual("ARB-AVAX", actions[0].symbol)
        self.assertEqual("time_stop", actions[0].reason)
        self.assertEqual(0, len(self.db.get_open_pairs_positions()))

        cursor = self.db._conn.execute("SELECT exit_reason FROM pairs_trades WHERE pair_key='ARB-AVAX'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual("time_stop", row[0])


if __name__ == "__main__":
    unittest.main()
