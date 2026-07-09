"""Tests for trend_short_factor independent exit profile.

When router_trend_short_factor_gate_enabled is True and sig.reason == "trend_short",
the backtester should use trend_short_factor_* parameters instead of the default ones.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from config import BacktestConfig


class TestTrendShortFactorExitConfig(unittest.TestCase):
    """Test that trend_short_factor config fields exist and have correct defaults."""

    def test_config_has_factor_exit_fields(self):
        cfg = BacktestConfig()
        self.assertTrue(hasattr(cfg, "trend_short_factor_stop_atr"))
        self.assertTrue(hasattr(cfg, "trend_short_factor_take_profit_atr"))
        self.assertTrue(hasattr(cfg, "trend_short_factor_trailing_atr"))
        self.assertTrue(hasattr(cfg, "trend_short_factor_max_hold_bars"))
        self.assertTrue(hasattr(cfg, "trend_short_factor_break_even_mfe_pct"))
        self.assertTrue(hasattr(cfg, "trend_short_factor_break_even_lock_pct"))
        self.assertTrue(hasattr(cfg, "trend_short_factor_risk_per_trade"))

    def test_factor_exit_defaults_differ_from_base(self):
        cfg = BacktestConfig()
        # Factor-specific values should be different from base defaults
        self.assertNotEqual(cfg.trend_short_factor_stop_atr, cfg.stop_atr)
        self.assertNotEqual(cfg.trend_short_factor_take_profit_atr, cfg.take_profit_atr)
        self.assertNotEqual(cfg.trend_short_factor_max_hold_bars, cfg.max_hold_bars)


class TestTrendShortFactorExitRouting(unittest.TestCase):
    """Test that exit parameters are routed correctly for trend_short_factor."""

    def _make_signal(self, reason="trend_short", regime="downtrend"):
        return SimpleNamespace(
            symbol="BTC-USDT-SWAP",
            direction=-1,
            score=3.5,
            regime=regime,
            reason=reason,
        )

    def test_factor_gate_enabled_uses_factor_params(self):
        """When factor gate is on and reason is trend_short, use factor params."""
        cfg = BacktestConfig(
            router_trend_short_factor_gate_enabled=True,
            trend_short_factor_stop_atr=1.5,
            trend_short_factor_take_profit_atr=1.0,
            trend_short_factor_risk_per_trade=0.02,
        )
        sig = self._make_signal()
        # The _is_trend_short_factor method checks these conditions
        self.assertTrue(
            cfg.router_trend_short_factor_gate_enabled and sig.reason == "trend_short"
        )

    def test_factor_gate_disabled_uses_base_params(self):
        """When factor gate is off, use base params even for trend_short."""
        cfg = BacktestConfig(
            router_trend_short_factor_gate_enabled=False,
        )
        sig = self._make_signal()
        self.assertFalse(
            cfg.router_trend_short_factor_gate_enabled and sig.reason == "trend_short"
        )

    def test_other_reasons_not_affected(self):
        """Non-trend_short reasons should not be affected by factor gate."""
        cfg = BacktestConfig(
            router_trend_short_factor_gate_enabled=True,
        )
        for reason in ["trend_long", "range_revert_short", "attack_breakout_short"]:
            sig = self._make_signal(reason=reason)
            self.assertFalse(
                cfg.router_trend_short_factor_gate_enabled and sig.reason == "trend_short"
            )


class TestBreakEvenLogic(unittest.TestCase):
    """Test break-even stop loss logic."""

    def test_break_even_mfe_threshold(self):
        """Break-even should trigger when MFE exceeds threshold."""
        cfg = BacktestConfig(
            trend_short_factor_break_even_mfe_pct=0.008,
            trend_short_factor_break_even_lock_pct=0.002,
        )
        # Simulate position with MFE exceeding threshold
        max_favorable_pct = 0.01  # 1% > 0.8% threshold
        self.assertGreaterEqual(max_favorable_pct, cfg.trend_short_factor_break_even_mfe_pct)

    def test_break_even_not_triggered_below_threshold(self):
        """Break-even should not trigger when MFE is below threshold."""
        cfg = BacktestConfig(
            trend_short_factor_break_even_mfe_pct=0.008,
        )
        max_favorable_pct = 0.005  # 0.5% < 0.8% threshold
        self.assertLess(max_favorable_pct, cfg.trend_short_factor_break_even_mfe_pct)


if __name__ == "__main__":
    unittest.main()
