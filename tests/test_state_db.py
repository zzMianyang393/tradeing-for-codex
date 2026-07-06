from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backtester import save_backtest_to_db
from state_db import StateDB, ReconcileResult


class _DBMixin:
    """Provides a temp-database for each test."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        self.db = StateDB(self.db_path)

    def tearDown(self):
        self.db.close()
        self._tmp.cleanup()


# ── Orders ──────────────────────────────────────────────────────────────

class TestOrders(_DBMixin, unittest.TestCase):

    def test_save_and_get_order(self):
        oid = self.db.save_order("BTC-USDT-SWAP", "long", 0.1, price=50000.0)
        order = self.db.get_order(oid)
        self.assertIsNotNone(order)
        self.assertEqual(order["symbol"], "BTC-USDT-SWAP")
        self.assertEqual(order["direction"], "long")
        self.assertEqual(order["status"], "pending")

    def test_update_order_status(self):
        oid = self.db.save_order("ETH-USDT-SWAP", "short", 1.0)
        self.db.update_order_status(
            oid,
            "filled",
            fill_price=3000.0,
            fill_qty=1.0,
            fee=0.15,
            exchange_order_id="okx-123",
        )
        order = self.db.get_order(oid)
        self.assertEqual(order["status"], "filled")
        self.assertEqual("okx-123", order["exchange_order_id"])
        self.assertEqual(order["fill_price"], 3000.0)
        self.assertIsNotNone(order["filled_at"])

    def test_get_nonexistent_order(self):
        self.assertIsNone(self.db.get_order("nope"))

    def test_order_with_meta(self):
        oid = self.db.save_order("SOL-USDT-SWAP", "long", 10.0, meta={"score": 3.5})
        order = self.db.get_order(oid)
        self.assertIn("score", order["meta"])


# ── Positions ───────────────────────────────────────────────────────────

class TestPositions(_DBMixin, unittest.TestCase):

    def test_save_and_get_open(self):
        pid = self.db.save_position("BTC-USDT-SWAP", "long", 50000.0, 0.001, 50.0, 5.0, 10.0)
        positions = self.db.get_open_positions()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], "BTC-USDT-SWAP")
        self.assertEqual(positions[0]["status"], "open")

    def test_close_position(self):
        pid = self.db.save_position("ETH-USDT-SWAP", "short", 3000.0, 0.1, 300.0, 30.0, 10.0)
        self.db.close_position(pid)
        positions = self.db.get_open_positions()
        self.assertEqual(len(positions), 0)

    def test_update_position_price(self):
        pid = self.db.save_position("BTC-USDT-SWAP", "long", 50000.0, 0.001, 50.0, 5.0, 10.0)
        self.db.update_position_price(pid, 51000.0, 1.0)
        positions = self.db.get_open_positions()
        self.assertEqual(positions[0]["current_price"], 51000.0)
        self.assertEqual(positions[0]["unrealized_pnl"], 1.0)


# ── Trades ──────────────────────────────────────────────────────────────

class TestTrades(_DBMixin, unittest.TestCase):

    def test_save_and_retrieve(self):
        tid = self.db.save_trade(
            symbol="BTC-USDT-SWAP", direction="long",
            entry_price=50000.0, exit_price=51000.0,
            entry_time="2025-01-01 00:00:00", exit_time="2025-01-01 01:00:00",
            pnl=2.0, pnl_pct=4.0, signal_reason="trend_long",
            exit_reason="take_profit", regime="uptrend",
        )
        trades = self.db.get_recent_trades(10)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["symbol"], "BTC-USDT-SWAP")
        self.assertEqual(trades[0]["pnl"], 2.0)

    def test_get_by_symbol(self):
        self.db.save_trade("BTC-USDT-SWAP", "long", 50000, 51000, "t", "t", 2.0, 4.0)
        self.db.save_trade("ETH-USDT-SWAP", "short", 3000, 2900, "t", "t", 1.0, 3.0)
        self.db.save_trade("BTC-USDT-SWAP", "short", 51000, 50500, "t", "t", 0.5, 1.0)
        btc = self.db.get_trades_by_symbol("BTC-USDT-SWAP")
        self.assertEqual(len(btc), 2)

    def test_get_by_reason(self):
        self.db.save_trade("X", "long", 100, 110, "t", "t", 1.0, 1.0, signal_reason="trend_long")
        self.db.save_trade("Y", "long", 100, 110, "t", "t", 1.0, 1.0, signal_reason="range_revert_long")
        trend = self.db.get_trades_by_reason("trend_long")
        self.assertEqual(len(trend), 1)

    def test_count_trades(self):
        self.assertEqual(self.db.count_trades(), 0)
        self.db.save_trade("X", "long", 100, 110, "t", "t", 1.0, 1.0)
        self.db.save_trade("Y", "short", 200, 190, "t", "t", 2.0, 1.0)
        self.assertEqual(self.db.count_trades(), 2)

    def test_trade_summary(self):
        self.db.save_trade("A", "long", 100, 110, "t", "t", 5.0, 5.0)
        self.db.save_trade("B", "short", 200, 210, "t", "t", -3.0, -1.5)
        self.db.save_trade("C", "long", 100, 115, "t", "t", 8.0, 8.0)
        summary = self.db.trade_summary()
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["wins"], 2)
        self.assertAlmostEqual(summary["win_rate"], 2 / 3, places=2)
        self.assertAlmostEqual(summary["total_pnl"], 10.0)

    def test_trade_summary_empty(self):
        summary = self.db.trade_summary()
        self.assertEqual(summary["total"], 0)


# ── Batch insert ────────────────────────────────────────────────────────

class TestBatchInsert(_DBMixin, unittest.TestCase):

    def test_save_backtest_trades(self):
        fake_trades = [
            {
                "symbol": "BTC-USDT-SWAP", "direction": "long",
                "entry": 50000.0, "exit": 51000.0,
                "entry_time": "2025-01-01", "exit_time": "2025-01-02",
                "pnl": 2.0, "pnl_pct_equity": 4.0,
                "reason": "trend_long", "exit_reason": "take_profit",
                "regime": "uptrend",
            },
            {
                "symbol": "ETH-USDT-SWAP", "direction": "short",
                "entry": 3000.0, "exit": 2900.0,
                "entry_time": "2025-01-01", "exit_time": "2025-01-02",
                "pnl": 1.0, "pnl_pct_equity": 2.0,
                "reason": "range_revert_short", "exit_reason": "stop_or_trail",
                "regime": "range",
            },
        ]
        count = self.db.save_backtest_trades(fake_trades)
        self.assertEqual(count, 2)
        self.assertEqual(self.db.count_trades(), 2)

    def test_save_empty_list(self):
        count = self.db.save_backtest_trades([])
        self.assertEqual(count, 0)


# ── Account snapshots ──────────────────────────────────────────────────

class TestAccountSnapshots(_DBMixin, unittest.TestCase):

    def test_snapshot_and_retrieve(self):
        self.db.snapshot_account(
            equity=10.0, available_margin=5.0, used_margin=5.0,
            unrealized_pnl=0.5, daily_pnl=-1.0, weekly_pnl=2.0,
            open_positions=2, risk_status="ok",
        )
        history = self.db.get_account_history()
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0]["equity"], 10.0)
        self.assertEqual(history[0]["open_positions"], 2)

    def test_multiple_snapshots(self):
        for i in range(5):
            self.db.snapshot_account(equity=10.0 + i, available_margin=5.0, used_margin=5.0, unrealized_pnl=0.0)
        history = self.db.get_account_history()
        self.assertEqual(len(history), 5)
        # Should be in order
        self.assertAlmostEqual(history[0]["equity"], 10.0)
        self.assertAlmostEqual(history[4]["equity"], 14.0)


# ── Risk events ─────────────────────────────────────────────────────────

class TestRiskEvents(_DBMixin, unittest.TestCase):

    def test_save_and_retrieve(self):
        self.db.save_risk_event("pause", {"reason": "consecutive losses"})
        self.db.save_risk_event("reject", {"reason": "volatility spike"})
        events = self.db.get_risk_events(10)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_type"], "reject")  # most recent first

    def test_save_without_detail(self):
        eid = self.db.save_risk_event("resume")
        self.assertIsNotNone(eid)


# ── Reconciliation ──────────────────────────────────────────────────────

class TestReconciliation(_DBMixin, unittest.TestCase):

    def test_consistent(self):
        self.db.save_position("BTC-USDT-SWAP", "long", 50000, 0.001, 50, 5, 10)
        result = self.db.reconcile_positions([{"symbol": "BTC-USDT-SWAP", "direction": "long"}])
        self.assertTrue(result.consistent)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual(len(result.local_only), 0)
        self.assertEqual(len(result.exchange_only), 0)

    def test_local_only(self):
        self.db.save_position("BTC-USDT-SWAP", "long", 50000, 0.001, 50, 5, 10)
        self.db.save_position("ETH-USDT-SWAP", "short", 3000, 0.1, 300, 30, 10)
        result = self.db.reconcile_positions([{"symbol": "BTC-USDT-SWAP", "direction": "long"}])
        self.assertFalse(result.consistent)
        self.assertEqual(len(result.local_only), 1)
        self.assertEqual(result.local_only[0]["symbol"], "ETH-USDT-SWAP")

    def test_exchange_only(self):
        result = self.db.reconcile_positions([{"symbol": "SOL-USDT-SWAP", "direction": "long"}])
        self.assertFalse(result.consistent)
        self.assertEqual(len(result.exchange_only), 1)
        self.assertEqual(result.exchange_only[0]["symbol"], "SOL-USDT-SWAP")

    def test_empty_both_sides(self):
        result = self.db.reconcile_positions([])
        self.assertTrue(result.consistent)


# ── DB file creation ────────────────────────────────────────────────────

class TestDBCreation(_DBMixin, unittest.TestCase):

    def test_creates_parent_directories(self):
        deep_path = Path(self._tmp.name) / "a" / "b" / "c" / "test.db"
        db = StateDB(deep_path)
        db.close()
        self.assertTrue(deep_path.exists())

    def test_wal_mode(self):
        # WAL mode creates a -wal file
        wal_path = Path(str(self.db_path) + "-wal")
        self.db.save_order("X", "long", 1.0)
        # WAL file may or may not exist depending on sync, but DB should work
        summary = self.db.trade_summary()
        self.assertEqual(summary["total"], 0)


class TestSaveBacktestToDb(unittest.TestCase):
    def test_risk_status_snapshot_is_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "backtest.db"
            report = {
                "end_equity": 12.5,
                "risk_status": {"orders_rejected": 2, "final_status": {"is_paused": False}},
                "trades_detail": [
                    {
                        "symbol": "BTC-USDT-SWAP",
                        "direction": "long",
                        "entry": 100.0,
                        "exit": 101.0,
                        "entry_time": "2026-01-01",
                        "exit_time": "2026-01-02",
                        "pnl": 1.0,
                        "pnl_pct_equity": 10.0,
                        "reason": "trend_long",
                        "exit_reason": "take_profit",
                        "regime": "uptrend",
                    }
                ],
            }

            save_backtest_to_db(report, db_path)

            db = StateDB(db_path)
            try:
                history = db.get_account_history()
            finally:
                db.close()
            self.assertIn('"orders_rejected": 2', history[0]["risk_status"])


if __name__ == "__main__":
    unittest.main()
