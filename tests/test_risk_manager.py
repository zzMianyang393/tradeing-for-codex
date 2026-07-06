from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from config import BacktestConfig
from risk_manager import RiskDecision, RiskManager, RiskStatus


def _cfg(**overrides):
    """BacktestConfig with sensible risk-manager defaults for testing."""
    defaults = dict(
        rm_enabled=True,
        rm_max_single_position_pct=0.40,
        rm_max_total_position_pct=0.80,
        rm_max_daily_loss_pct=15.0,
        rm_max_weekly_loss_pct=30.0,
        rm_consecutive_loss_pause=4,
        rm_consecutive_loss_pause_bars=288,
        rm_volatility_halt_threshold=0.06,
        rm_min_liquidation_distance_pct=0.05,
    )
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def _bars(atr_pct=0.02):
    bar = MagicMock()
    bar.atr_pct = atr_pct
    bar.close = 100.0
    return [bar]


def _bars_with_order_book(
    spread_pct=0.001,
    bid_depth_quote=10_000.0,
    ask_depth_quote=10_000.0,
    atr_pct=0.02,
):
    bar = MagicMock()
    bar.atr_pct = atr_pct
    bar.close = 100.0
    bar.order_book_spread_pct = spread_pct
    bar.bid_depth_quote = bid_depth_quote
    bar.ask_depth_quote = ask_depth_quote
    return [bar]


class TestNormalOrder(unittest.TestCase):
    def test_small_order_passes(self):
        rm = RiskManager(_cfg())
        # notional=3, equity=10 → 30% < 40%
        d = rm.check_order("BTC-USDT-SWAP", 1, 3.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "")

    def test_returns_risk_decision_dataclass(self):
        rm = RiskManager(_cfg())
        d = rm.check_order("BTC-USDT-SWAP", 1, 3.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertIsInstance(d, RiskDecision)


class TestSinglePositionLimit(unittest.TestCase):
    def test_rejected_when_exceeding(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=0.40))
        # notional/equity = 50/100 = 0.50 > 0.40
        d = rm.check_order("BTC-USDT-SWAP", 1, 50.0, 5.0, 100.0, 0, _bars(), 0)
        self.assertFalse(d.allowed)
        self.assertIn("single position", d.reason)

    def test_accepted_when_within(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=0.40))
        # notional/equity = 30/100 = 0.30 < 0.40
        d = rm.check_order("BTC-USDT-SWAP", 1, 30.0, 3.0, 100.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)

    def test_accepted_at_boundary(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=0.40))
        # exactly at the boundary — notional/equity = 0.40, should be allowed (not >)
        d = rm.check_order("BTC-USDT-SWAP", 1, 40.0, 4.0, 100.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)


class TestTotalPositionLimit(unittest.TestCase):
    def test_rejected_when_external_current_margin_exceeds(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_total_position_pct=0.80))
        # Backtester passes the current open-position margin instead of
        # requiring RiskManager to reconstruct it from private state.
        d = rm.check_order(
            "BTC-USDT-SWAP",
            1,
            10.0,
            5.0,
            10.0,
            0,
            _bars(),
            0,
            current_positions_margin=7.0,
            current_positions_count=1,
        )
        self.assertFalse(d.allowed)
        self.assertIn("total position", d.reason)

    def test_rejected_when_existing_plus_new_exceeds(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_total_position_pct=0.80))
        rm._track_open("ETH-USDT-SWAP", 7.0)
        # (7.0 + 5.0) / 10.0 = 1.20 > 0.80
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 5.0, 10.0, 0, _bars(), 0)
        self.assertFalse(d.allowed)
        self.assertIn("total position", d.reason)

    def test_accepted_when_within(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_total_position_pct=0.80))
        rm._track_open("ETH-USDT-SWAP", 5.0)
        # (5.0 + 3.0) / 10.0 = 0.80, not > 0.80
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 3.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)

    def test_no_existing_positions(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_total_position_pct=0.80))
        # 2.0 / 10.0 = 0.20 < 0.80
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 2.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)


class TestDailyLossLimit(unittest.TestCase):
    def test_rejected_when_loss_exceeds(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_daily_loss_pct=15.0))
        rm._daily_pnl = -2.0  # -2/10 = 20% > 15%
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertFalse(d.allowed)
        self.assertIn("daily loss", d.reason)

    def test_not_checked_when_profit(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_daily_loss_pct=15.0))
        rm._daily_pnl = 1.0
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)

    def test_not_checked_when_zero(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_daily_loss_pct=15.0))
        rm._daily_pnl = 0.0
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)

    def test_accepted_when_within(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_daily_loss_pct=15.0))
        rm._daily_pnl = -1.0  # -1/10 = 10% < 15%
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)


class TestWeeklyLossLimit(unittest.TestCase):
    def test_rejected_when_loss_exceeds(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_weekly_loss_pct=30.0))
        rm._weekly_pnl = -4.0  # -4/10 = 40% > 30%
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertFalse(d.allowed)
        self.assertIn("weekly loss", d.reason)

    def test_not_checked_when_profit(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_weekly_loss_pct=30.0))
        rm._weekly_pnl = 5.0
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)

    def test_accepted_when_within(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_weekly_loss_pct=30.0))
        rm._weekly_pnl = -2.0  # -2/10 = 20% < 30%
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)


class TestConsecutiveLossPause(unittest.TestCase):
    def test_triggers_pause(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_consecutive_loss_pause=4, rm_consecutive_loss_pause_bars=100))
        rm._consecutive_losses = 4
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertFalse(d.allowed)
        self.assertIn("consecutive losses", d.reason)
        self.assertTrue(rm._is_paused)

    def test_not_triggered_below_threshold(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_consecutive_loss_pause=4))
        rm._consecutive_losses = 3
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)

    def test_increments_pauses_count(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_consecutive_loss_pause=1, rm_consecutive_loss_pause_bars=100))
        rm._consecutive_losses = 1
        rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertEqual(rm._pauses_count, 1)


class TestVolatilityHalt(unittest.TestCase):
    def test_triggers_pause_when_exceeding(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_volatility_halt_threshold=0.06))
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(atr_pct=0.08), 0)
        self.assertFalse(d.allowed)
        self.assertIn("volatility", d.reason)
        self.assertTrue(rm._is_paused)

    def test_accepted_when_within(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_volatility_halt_threshold=0.06))
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(atr_pct=0.04), 0)
        self.assertTrue(d.allowed)

    def test_exactly_at_threshold(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_volatility_halt_threshold=0.06))
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(atr_pct=0.06), 0)
        self.assertTrue(d.allowed)


class TestOrderBookLiquidityFilter(unittest.TestCase):
    def test_rejects_when_order_book_spread_is_too_wide(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_max_order_book_spread_pct=0.003))

        d = rm.check_order(
            "BTC-USDT-SWAP",
            1,
            10.0,
            1.0,
            100.0,
            0,
            _bars_with_order_book(spread_pct=0.005),
            0,
        )

        self.assertFalse(d.allowed)
        self.assertIn("order book spread", d.reason)

    def test_rejects_when_directional_depth_is_too_thin(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_min_order_book_depth_quote=1_000.0))

        d = rm.check_order(
            "BTC-USDT-SWAP",
            1,
            10.0,
            1.0,
            100.0,
            0,
            _bars_with_order_book(ask_depth_quote=500.0),
            0,
        )

        self.assertFalse(d.allowed)
        self.assertIn("order book depth", d.reason)

    def test_short_orders_check_bid_depth(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_min_order_book_depth_quote=1_000.0))

        d = rm.check_order(
            "BTC-USDT-SWAP",
            -1,
            10.0,
            1.0,
            100.0,
            0,
            _bars_with_order_book(bid_depth_quote=500.0),
            0,
        )

        self.assertFalse(d.allowed)
        self.assertIn("order book depth", d.reason)

    def test_missing_order_book_features_do_not_block_by_default(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0))

        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 100.0, 0, _bars(), 0)

        self.assertTrue(d.allowed)


class TestLiquidationDistance(unittest.TestCase):
    def test_rejected_when_too_close(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=10.0, rm_min_liquidation_distance_pct=0.05))
        # margin/notional = 1/100 = 0.01 < 0.05
        d = rm.check_order("BTC-USDT-SWAP", 1, 100.0, 1.0, 1000.0, 0, _bars(), 0)
        self.assertFalse(d.allowed)
        self.assertIn("liquidation distance", d.reason)

    def test_accepted_when_far_enough(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=10.0, rm_min_liquidation_distance_pct=0.05))
        # margin/notional = 10/100 = 0.10 > 0.05
        d = rm.check_order("BTC-USDT-SWAP", 1, 100.0, 10.0, 1000.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)

    def test_skipped_when_notional_zero(self):
        rm = RiskManager(_cfg(rm_min_liquidation_distance_pct=0.05))
        d = rm.check_order("BTC-USDT-SWAP", 1, 0.0, 0.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)


class TestPauseRejectsAll(unittest.TestCase):
    def test_paused_rejects(self):
        rm = RiskManager(_cfg(rm_consecutive_loss_pause_bars=100))
        rm._is_paused = True
        rm._pause_reason = "test"
        rm._pause_until_step = 100
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 50, _bars(), 0)
        self.assertFalse(d.allowed)
        self.assertIn("paused", d.reason)

    def test_paused_counts_rejection(self):
        rm = RiskManager(_cfg(rm_consecutive_loss_pause_bars=100))
        rm._is_paused = True
        rm._pause_reason = "test"
        rm._pause_until_step = 100
        rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 50, _bars(), 0)
        self.assertEqual(rm._rejections_count, 1)


class TestPauseExpiry(unittest.TestCase):
    def test_pause_clears_at_expiry_step(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_consecutive_loss_pause_bars=100))
        rm._is_paused = True
        rm._pause_reason = "test"
        rm._pause_until_step = 100
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 100, _bars(), 0)
        self.assertTrue(d.allowed)
        self.assertFalse(rm._is_paused)
        self.assertEqual(rm._pause_reason, "")

    def test_still_paused_one_step_before(self):
        rm = RiskManager(_cfg(rm_consecutive_loss_pause_bars=100))
        rm._is_paused = True
        rm._pause_reason = "test"
        rm._pause_until_step = 100
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 99, _bars(), 0)
        self.assertFalse(d.allowed)

    def test_can_open_after_resume(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_consecutive_loss_pause_bars=10))
        rm._is_paused = True
        rm._pause_reason = "test"
        rm._pause_until_step = 5
        # Resume at step 5
        rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 5, _bars(), 0)
        self.assertFalse(rm._is_paused)
        # Should be able to open now
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 5, _bars(), 0)
        self.assertTrue(d.allowed)


class TestRmDisabled(unittest.TestCase):
    def test_all_checks_skipped(self):
        rm = RiskManager(_cfg(rm_enabled=False))
        rm._is_paused = True
        rm._pause_until_step = 999
        rm._consecutive_losses = 999
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(atr_pct=0.99), 0)
        self.assertTrue(d.allowed)

    def test_on_trade_close_still_works(self):
        rm = RiskManager(_cfg(rm_enabled=False))
        rm.on_trade_close(-1.0, 10, "BTC-USDT-SWAP", 5.0)
        self.assertEqual(rm._daily_pnl, -1.0)
        self.assertEqual(rm._consecutive_losses, 1)


class TestOnTradeClose(unittest.TestCase):
    def test_loss_increments_consecutive(self):
        rm = RiskManager(_cfg())
        rm.on_trade_close(-1.0, 10, "BTC-USDT-SWAP", 5.0)
        self.assertEqual(rm._consecutive_losses, 1)
        self.assertEqual(rm._daily_pnl, -1.0)
        self.assertEqual(rm._weekly_pnl, -1.0)

    def test_win_resets_consecutive(self):
        rm = RiskManager(_cfg())
        rm._consecutive_losses = 3
        rm.on_trade_close(2.0, 10, "BTC-USDT-SWAP", 5.0)
        self.assertEqual(rm._consecutive_losses, 0)

    def test_accumulates_pnl(self):
        rm = RiskManager(_cfg())
        rm.on_trade_close(-1.0, 10, "A", 1.0)
        rm.on_trade_close(-0.5, 20, "B", 1.0)
        rm.on_trade_close(2.0, 30, "C", 1.0)
        self.assertAlmostEqual(rm._daily_pnl, 0.5)
        self.assertAlmostEqual(rm._weekly_pnl, 0.5)

    def test_removes_position_from_tracking(self):
        rm = RiskManager(_cfg())
        rm._track_open("BTC-USDT-SWAP", 5.0)
        rm._track_open("ETH-USDT-SWAP", 3.0)
        self.assertAlmostEqual(rm._total_margin_used, 8.0)
        rm.on_trade_close(1.0, 10, "BTC-USDT-SWAP", 5.0)
        self.assertNotIn("BTC-USDT-SWAP", rm._open_margins)
        self.assertIn("ETH-USDT-SWAP", rm._open_margins)
        self.assertAlmostEqual(rm._total_margin_used, 3.0)

    def test_pnl_zero_resets_consecutive(self):
        rm = RiskManager(_cfg())
        rm._consecutive_losses = 2
        rm.on_trade_close(0.0, 10, "BTC-USDT-SWAP", 1.0)
        self.assertEqual(rm._consecutive_losses, 0)


class TestReset(unittest.TestCase):
    def test_clears_all_state(self):
        rm = RiskManager(_cfg())
        rm._daily_pnl = -5.0
        rm._weekly_pnl = -10.0
        rm._consecutive_losses = 5
        rm._is_paused = True
        rm._pause_reason = "test"
        rm._open_margins["BTC-USDT-SWAP"] = 3.0
        rm._pauses_count = 2
        rm._rejections_count = 5

        rm.reset()

        self.assertEqual(rm._daily_pnl, 0.0)
        self.assertEqual(rm._weekly_pnl, 0.0)
        self.assertEqual(rm._consecutive_losses, 0)
        self.assertFalse(rm._is_paused)
        self.assertEqual(rm._pause_reason, "")
        self.assertEqual(len(rm._open_margins), 0)
        self.assertEqual(rm._pauses_count, 0)
        self.assertEqual(rm._rejections_count, 0)


class TestGetStatus(unittest.TestCase):
    def test_reflects_current_state(self):
        rm = RiskManager(_cfg())
        rm._daily_pnl = -1.0
        rm._weekly_pnl = -2.0
        rm._consecutive_losses = 3
        rm._track_open("BTC-USDT-SWAP", 5.0)

        status = rm.get_status()

        self.assertIsInstance(status, RiskStatus)
        self.assertEqual(status.daily_pnl, -1.0)
        self.assertEqual(status.weekly_pnl, -2.0)
        self.assertEqual(status.consecutive_losses, 3)
        self.assertEqual(status.open_positions_count, 1)
        self.assertAlmostEqual(status.total_margin_used, 5.0)
        self.assertFalse(status.is_paused)

    def test_pause_status(self):
        rm = RiskManager(_cfg())
        rm._is_paused = True
        rm._pause_reason = "volatility"
        rm._pause_until_step = 200

        status = rm.get_status()
        self.assertTrue(status.is_paused)
        self.assertEqual(status.pause_reason, "volatility")
        self.assertEqual(status.pause_until_step, 200)


class TestEdgeCases(unittest.TestCase):
    def test_zero_equity_skips_division_checks(self):
        rm = RiskManager(_cfg())
        d = rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 0.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)

    def test_rejection_counter_increments(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=0.10))
        rm.check_order("BTC-USDT-SWAP", 1, 50.0, 5.0, 100.0, 0, _bars(), 0)
        rm.check_order("BTC-USDT-SWAP", 1, 50.0, 5.0, 100.0, 0, _bars(), 0)
        self.assertEqual(rm._rejections_count, 2)

    def test_pause_blocks_subsequent_same_step_calls(self):
        """After a volatility halt at step N, another check at step N is also blocked."""
        rm = RiskManager(_cfg(rm_max_single_position_pct=1.0, rm_volatility_halt_threshold=0.06))
        rm.check_order("BTC-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(atr_pct=0.08), 0)
        self.assertTrue(rm._is_paused)
        d = rm.check_order("ETH-USDT-SWAP", 1, 10.0, 1.0, 10.0, 0, _bars(atr_pct=0.01), 0)
        self.assertFalse(d.allowed)
        self.assertIn("paused", d.reason)

    def test_check_order_short_direction(self):
        """RiskManager doesn't care about direction; it checks position sizing."""
        rm = RiskManager(_cfg())
        d = rm.check_order("BTC-USDT-SWAP", -1, 3.0, 1.0, 10.0, 0, _bars(), 0)
        self.assertTrue(d.allowed)


if __name__ == "__main__":
    unittest.main()
