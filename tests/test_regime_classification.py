"""Tests for configurable regime classification.

Verifies that regime thresholds can be adjusted via config to widen
the transition band and increase signal frequency.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from strategy import classify_regime


def _make_bar(**kwargs):
    defaults = dict(
        ema50=100.0,
        ema200=99.0,
        trend_strength=1.0,
        atr_pct=0.02,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestDefaultRegimeClassification(unittest.TestCase):
    """Test default regime thresholds."""

    def test_strong_uptrend(self):
        bar = _make_bar(ema50=102.0, ema200=98.0, trend_strength=1.5)
        self.assertEqual(classify_regime(bar), "uptrend")

    def test_strong_downtrend(self):
        bar = _make_bar(ema50=98.0, ema200=102.0, trend_strength=-1.5)
        self.assertEqual(classify_regime(bar), "downtrend")

    def test_transition_band(self):
        # trend_strength 0.9-1.2 = transition
        bar = _make_bar(ema50=101.0, ema200=99.0, trend_strength=1.0, atr_pct=0.01)
        self.assertEqual(classify_regime(bar), "transition")

    def test_range_low_strength(self):
        bar = _make_bar(ema50=100.0, ema200=100.5, trend_strength=0.5, atr_pct=0.01)
        self.assertEqual(classify_regime(bar), "range")


class TestConfigurableRegimeClassification(unittest.TestCase):
    """Test that config can widen the transition band."""

    def test_wider_transition_band(self):
        """Lower uptrend threshold widens transition band."""
        config = SimpleNamespace(
            regime_uptrend_threshold=1.0,
            regime_downtrend_threshold=-1.0,
            regime_range_strength_max=0.7,
            regime_range_atr_pct_max=0.0045,
        )
        # trend_strength=1.0 would be transition with default (1.2), but uptrend with lowered threshold
        bar = _make_bar(ema50=101.0, ema200=99.0, trend_strength=1.05, atr_pct=0.01)
        self.assertEqual(classify_regime(bar, config), "uptrend")

    def test_wider_transition_band_mid(self):
        """With wider config, 0.75 trend_strength becomes transition."""
        config = SimpleNamespace(
            regime_uptrend_threshold=1.0,
            regime_downtrend_threshold=-1.0,
            regime_range_strength_max=0.7,
            regime_range_atr_pct_max=0.0045,
        )
        bar = _make_bar(ema50=101.0, ema200=99.0, trend_strength=0.75, atr_pct=0.01)
        self.assertEqual(classify_regime(bar, config), "transition")

    def test_no_config_uses_defaults(self):
        """Without config, use default thresholds."""
        bar = _make_bar(ema50=101.0, ema200=99.0, trend_strength=1.0, atr_pct=0.01)
        self.assertEqual(classify_regime(bar), "transition")
        self.assertEqual(classify_regime(bar, None), "transition")


if __name__ == "__main__":
    unittest.main()
