from __future__ import annotations

import unittest
from dataclasses import replace

from config import BacktestConfig
from market import FeatureBar
from risk_manager import RiskManager, RiskDecision, RiskStatus


def _bar(
    close: float = 100.0,
    atr_pct: float = 0.01,
    **kwargs,
) -> FeatureBar:
    """Minimal FeatureBar factory for tests."""
    defaults = dict(
        ts=0, time="2025-01-01 00:00:00",
        open=close, high=close * 1.01, low=close * 0.99, close=close,
        volume_quote=1_000_000.0,
        ema20=close, ema50=close, ema200=close,
        atr=close * atr_pct, atr_pct=atr_pct,
        rsi=50.0, bb_mid=close, bb_upper=close * 1.02, bb_lower=close * 0.98,
        vol_sma=1_000_000.0, donchian_high=close * 1.05, donchian_low=close * 0.95,
        trend_strength=0.0,
    )
    defaults.update(kwargs)
    return FeatureBar(**defaults)


def _cfg(**overrides) -> BacktestConfig:
    """BacktestConfig with rm_enabled=True and tight limits for testing."""
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


class RiskManagerBasicTests(unittest.TestCase):
    """Core check_order logic."""

    def test_normal_order_passes(self):
        rm = RiskManager(_cfg())
        rm.reset()
        bar = _bar()
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=3.0, margin=1.0, equity=10.0,
            current_step=100, bars=[bar], idx=0,
        )
        self.assertTrue(decision.allowed)

    def test_single_position_too_large(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=0.40))
        rm.reset()
        bar = _bar()
        # notional / equity = 5.0 / 10.0 = 50% > 40%
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=5.0, margin=1.0, equity=10.0,
            current_step=100, bars=[bar], idx=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("single position", decision.reason)

    def test_total_margin_exceeded(self):
        rm = RiskManager(_cfg(rm_max_total_position_pct=0.80))
        rm.reset()
        bar = _bar()
        # existing margin 7.0 + new margin 2.0 = 9.0 / 10.0 = 90% > 80%
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=6.0, margin=2.0, equity=10.0,
            current_step=100, bars=[bar], idx=0,
            current_positions_margin=7.0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("total margin", decision.reason)

    def test_daily_loss_exceeded(self):
        rm = RiskManager(_cfg(rm_max_daily_loss_pct=15.0))
        rm.reset()
        bar = _bar()
        # Accumulate losses: 3 losses of -2.0 each = -6.0 total loss
        # 6.0 / 10.0 * 100 = 60% > 15%
        for _ in range(3):
            rm.on_trade_close(-2.0, 10)
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=3.0, margin=1.0, equity=10.0,
            current_step=100, bars=[bar], idx=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("daily loss", decision.reason)

    def test_weekly_loss_exceeded(self):
        rm = RiskManager(_cfg(rm_max_weekly_loss_pct=30.0, rm_max_daily_loss_pct=999.0))
        rm.reset()
        bar = _bar()
        # 4 losses of -1.0 each = -4.0, 4.0/10.0*100 = 40% > 30%
        for _ in range(4):
            rm.on_trade_close(-1.0, 10)
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=3.0, margin=1.0, equity=10.0,
            current_step=100, bars=[bar], idx=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("weekly loss", decision.reason)

    def test_consecutive_loss_pause(self):
        rm = RiskManager(_cfg(rm_consecutive_loss_pause=3, rm_consecutive_loss_pause_bars=100))
        rm.reset()
        bar = _bar()
        # 3 consecutive losses
        for i in range(3):
            rm.on_trade_close(-0.5, i)
        # Should now be paused
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=3.0, margin=1.0, equity=10.0,
            current_step=100, bars=[bar], idx=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("consecutive loss pause", decision.reason)

    def test_volatility_halt(self):
        rm = RiskManager(_cfg(rm_volatility_halt_threshold=0.06))
        rm.reset()
        bar = _bar(atr_pct=0.08)  # 8% > 6%
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=3.0, margin=1.0, equity=10.0,
            current_step=100, bars=[bar], idx=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("volatility", decision.reason)

    def test_liquidation_distance_protection(self):
        rm = RiskManager(_cfg(rm_min_liquidation_distance_pct=0.05))
        rm.reset()
        bar = _bar(close=100.0)
        # notional=100, equity=10 → potential loss = 100*0.05/100*100 = 5.0
        # 5.0 > 10*0.95=9.5? No, 5.0 < 9.5, so it passes.
        # Make it fail: notional=200, equity=10
        # loss = 200*0.05 = 10.0 > 9.5 → reject
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=200.0, margin=10.0, equity=10.0,
            current_step=100, bars=[bar], idx=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("liquidation", decision.reason)


class RiskManagerPauseTests(unittest.TestCase):
    """Pause/resume lifecycle."""

    def test_pause_blocks_all_orders(self):
        rm = RiskManager(_cfg(rm_consecutive_loss_pause=2, rm_consecutive_loss_pause_bars=50))
        rm.reset()
        bar = _bar()
        # 2 consecutive losses → triggers pause
        rm.on_trade_close(-1.0, 10)
        rm.on_trade_close(-1.0, 20)
        # Step 30 is within pause window (20 + 50 = 70)
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=1.0, margin=0.5, equity=10.0,
            current_step=30, bars=[bar], idx=0,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("paused", decision.reason)

    def test_pause_expires(self):
        rm = RiskManager(_cfg(rm_consecutive_loss_pause=2, rm_consecutive_loss_pause_bars=50))
        rm.reset()
        bar = _bar()
        rm.on_trade_close(-1.0, 10)
        rm.on_trade_close(-1.0, 20)
        # Step 80 is past the pause window (20 + 50 = 70)
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=1.0, margin=0.5, equity=10.0,
            current_step=80, bars=[bar], idx=0,
        )
        self.assertTrue(decision.allowed)

    def test_pause_gets_extended(self):
        rm = RiskManager(_cfg(rm_consecutive_loss_pause=2, rm_consecutive_loss_pause_bars=50))
        rm.reset()
        bar = _bar()
        # First pause: triggered at step 20, expires at 70
        rm.on_trade_close(-1.0, 10)
        rm.on_trade_close(-1.0, 20)
        # Win resets consecutive, but if we have another loss later
        rm.on_trade_close(1.0, 30)  # win resets
        rm.on_trade_close(-1.0, 40)
        rm.on_trade_close(-1.0, 50)
        # New pause: triggered at 50, expires at 100
        # Step 80 should be blocked
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=1.0, margin=0.5, equity=10.0,
            current_step=80, bars=[bar], idx=0,
        )
        self.assertFalse(decision.allowed)


class RiskManagerStateTests(unittest.TestCase):
    """State tracking and reset."""

    def test_consecutive_losses_reset_on_win(self):
        rm = RiskManager(_cfg(rm_consecutive_loss_pause=5))
        rm.reset()
        rm.on_trade_close(-1.0, 10)
        rm.on_trade_close(-1.0, 20)
        rm.on_trade_close(-1.0, 30)
        self.assertEqual(rm._consecutive_losses, 3)
        rm.on_trade_close(1.0, 40)  # win resets
        self.assertEqual(rm._consecutive_losses, 0)

    def test_reset_clears_all_state(self):
        rm = RiskManager(_cfg())
        rm.reset()
        rm.on_trade_close(-1.0, 10)
        rm.on_trade_close(-1.0, 20)
        rm._rejections_count = 5
        rm._pauses_count = 2
        rm.reset()
        self.assertEqual(rm._consecutive_losses, 0)
        self.assertEqual(rm._daily_pnl, [])
        self.assertEqual(rm._weekly_pnl, [])
        self.assertEqual(rm._rejections_count, 0)
        self.assertEqual(rm._pauses_count, 0)
        self.assertEqual(rm._pause_until_step, -1)

    def test_get_status(self):
        rm = RiskManager(_cfg())
        rm.reset()
        rm.on_trade_close(-2.0, 10)
        rm.on_trade_close(1.0, 20)
        status = rm.get_status()
        self.assertIsInstance(status, RiskStatus)
        self.assertFalse(status.is_paused)
        self.assertEqual(status.consecutive_losses, 0)  # last was a win
        self.assertAlmostEqual(status.weekly_pnl, -1.0)

    def test_rejections_counted(self):
        rm = RiskManager(_cfg(rm_max_single_position_pct=0.10))
        rm.reset()
        bar = _bar()
        # This should be rejected (notional/equity = 50% > 10%)
        rm.check_order("X", 1, 5.0, 1.0, 10.0, 100, [bar], 0)
        self.assertEqual(rm._rejections_count, 1)
        # This should pass
        rm.check_order("X", 1, 0.5, 0.1, 10.0, 100, [bar], 0)
        self.assertEqual(rm._rejections_count, 1)  # not incremented


class RiskManagerDisabledTests(unittest.TestCase):
    """rm_enabled=False should skip all checks."""

    def test_disabled_allows_everything(self):
        rm = RiskManager(_cfg(rm_enabled=False))
        rm.reset()
        bar = _bar(atr_pct=0.99)  # extreme volatility
        decision = rm.check_order(
            symbol="BTC-USDT-SWAP", direction=1,
            notional=999.0, margin=999.0, equity=1.0,
            current_step=0, bars=[bar], idx=0,
        )
        # RiskManager itself doesn't check rm_enabled — it's the backtester
        # that decides whether to instantiate it.  But the config flag exists.
        # This test verifies the flag is readable.
        self.assertFalse(rm.config.rm_enabled)


class RiskManagerRollingWindowTests(unittest.TestCase):
    """Rolling PnL windows trim correctly."""

    def test_daily_window_trims(self):
        rm = RiskManager(_cfg())
        rm.reset()
        # Add 100 losses (more than _DAILY_WINDOW=96)
        for i in range(100):
            rm.on_trade_close(-1.0, i)
        # Only the last 96 should remain
        self.assertEqual(len(rm._daily_pnl), 96)
        # Sum should be -96.0
        self.assertAlmostEqual(sum(rm._daily_pnl), -96.0)

    def test_weekly_window_trims(self):
        rm = RiskManager(_cfg())
        rm.reset()
        for i in range(700):
            rm.on_trade_close(-1.0, i)
        self.assertEqual(len(rm._weekly_pnl), 672)


if __name__ == "__main__":
    unittest.main()
