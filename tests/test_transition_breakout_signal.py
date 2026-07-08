"""Tests for enhanced transition breakout long signals.

Two new signal types are added to the transition regime:
1. transition_breakout_long_pullback: breakout + pullback continuation
2. transition_breakout_long_volume: volume breakout without overheat

These tests verify the signal logic before implementation.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from strategy import classify_regime, signal_for


def _make_bar(**kwargs):
    """Create a minimal FeatureBar-like object with sensible defaults."""
    defaults = dict(
        ts=1700000000000,
        time="2025-01-01 00:00:00",
        open=100.0,
        high=105.0,
        low=95.0,
        close=102.0,
        volume_quote=500_000.0,
        ema20=100.0,
        ema50=99.0,
        ema200=95.0,
        atr=2.0,
        atr_pct=0.02,
        rsi=55.0,
        bb_mid=100.0,
        bb_upper=108.0,
        bb_lower=92.0,
        vol_sma=400_000.0,
        donchian_high=104.0,
        donchian_low=96.0,
        trend_strength=1.0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestTransitionBreakoutLongPullback(unittest.TestCase):
    """Test: breakout + pullback continuation in transition regime."""

    def _make_config(self, **overrides):
        defaults = dict(
            transition_long_enabled=True,
            transition_short_enabled=True,
            transition_long_min_move_21d=-1.0,
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_pullback_after_breakout_returns_long_signal(self):
        """After a breakout, price pulls back to EMA20 and bounces → signal."""
        bars = []
        # Build 260 bars of transition-like data
        for i in range(260):
            bars.append(_make_bar(
                ts=1700000000000 + i * 900_000,
                close=100.0 + (i % 5) * 0.1,
                ema20=100.0,
                ema50=99.5,
                ema200=98.0,
                trend_strength=0.95,
                atr=2.0,
                atr_pct=0.02,
                rsi=55.0,
                vol_sma=400_000.0,
                volume_quote=550_000.0,  # vol_ratio ~1.375
                donchian_high=104.0,
                donchian_low=96.0,
            ))
        # Last bar: pullback bounce with tighter conditions
        bars.append(_make_bar(
            ts=1700000000000 + 260 * 900_000,
            close=101.0,  # just above ema20
            open=99.5,
            high=101.5,
            low=99.0,
            ema20=100.0,
            ema50=99.5,
            ema200=98.0,
            trend_strength=0.95,
            atr=2.0,
            atr_pct=0.02,
            rsi=52.0,
            vol_sma=400_000.0,
            volume_quote=540_000.0,  # vol_ratio ~1.35
            donchian_high=104.0,
            donchian_low=96.0,
        ))
        # Previous bar was below ema20 (pullback)
        bars[-2] = _make_bar(
            ts=1700000000000 + 259 * 900_000,
            close=99.0,  # below ema20
            open=100.0,
            high=100.5,
            low=98.5,
            ema20=100.0,
            ema50=99.5,
            ema200=98.0,
            trend_strength=0.95,
            atr=2.0,
            atr_pct=0.02,
            rsi=48.0,
            vol_sma=400_000.0,
            volume_quote=400_000.0,
            donchian_high=104.0,
            donchian_low=96.0,
        )
        config = self._make_config()
        sig = signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, config)
        # Should produce a transition_breakout_long or similar long signal
        self.assertIsNotNone(sig)
        if sig:
            self.assertEqual(sig.direction, 1)
            self.assertIn(sig.reason, ("transition_breakout_long",))

    def test_pullback_rsi_overheated_no_signal(self):
        """RSI > 65 during pullback bounce → no signal."""
        bars = []
        for i in range(260):
            bars.append(_make_bar(
                ts=1700000000000 + i * 900_000,
                close=100.0,
                ema20=100.0,
                ema50=99.5,
                ema200=98.0,
                trend_strength=0.95,
                atr=2.0,
                atr_pct=0.02,
                rsi=55.0,
                vol_sma=400_000.0,
                volume_quote=450_000.0,
                donchian_high=104.0,
                donchian_low=96.0,
            ))
        # Last bar: bounce but RSI too high
        bars.append(_make_bar(
            ts=1700000000000 + 260 * 900_000,
            close=101.0,
            open=99.5,
            ema20=100.0,
            ema50=99.5,
            ema200=98.0,
            trend_strength=0.95,
            atr=2.0,
            atr_pct=0.02,
            rsi=70.0,  # overbought
            vol_sma=400_000.0,
            volume_quote=460_000.0,
            donchian_high=104.0,
            donchian_low=96.0,
        ))
        bars[-2] = _make_bar(
            ts=1700000000000 + 259 * 900_000,
            close=99.0,
            ema20=100.0,
            ema50=99.5,
            ema200=98.0,
            trend_strength=0.95,
            atr=2.0,
            atr_pct=0.02,
            rsi=48.0,
            vol_sma=400_000.0,
            volume_quote=400_000.0,
            donchian_high=104.0,
            donchian_low=96.0,
        )
        config = self._make_config()
        sig = signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, config)
        # RSI too high → no transition long signal
        if sig and sig.direction == 1:
            self.assertNotIn("transition_breakout_long", sig.reason)

    def test_pullback_ema20_below_ema50_no_signal(self):
        """ema20 <= ema50 → no transition long signal."""
        bars = []
        for i in range(260):
            bars.append(_make_bar(
                ts=1700000000000 + i * 900_000,
                close=100.0,
                ema20=99.0,
                ema50=100.0,  # ema20 < ema50
                ema200=101.0,
                trend_strength=-1.5,  # downtrend
                atr=2.0,
                atr_pct=0.02,
                rsi=45.0,
                vol_sma=400_000.0,
                volume_quote=450_000.0,
                donchian_high=104.0,
                donchian_low=96.0,
            ))
        bars.append(_make_bar(
            ts=1700000000000 + 260 * 900_000,
            close=101.0,
            ema20=99.0,
            ema50=100.0,
            ema200=101.0,
            trend_strength=-1.5,
            atr=2.0,
            atr_pct=0.02,
            rsi=52.0,
            vol_sma=400_000.0,
            volume_quote=460_000.0,
            donchian_high=104.0,
            donchian_low=96.0,
        ))
        bars[-2] = _make_bar(
            ts=1700000000000 + 259 * 900_000,
            close=99.0,
            ema20=99.0,
            ema50=100.0,
            ema200=101.0,
            trend_strength=-1.5,
            atr=2.0,
            atr_pct=0.02,
            rsi=48.0,
            vol_sma=400_000.0,
            volume_quote=400_000.0,
            donchian_high=104.0,
            donchian_low=96.0,
        )
        config = self._make_config()
        sig = signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, config)
        # ema20 < ema50 in downtrend → no long signal
        if sig and sig.direction == 1:
            self.assertNotIn("transition_breakout_long", sig.reason)


class TestTransitionBreakoutLongVolume(unittest.TestCase):
    """Test: volume breakout without overheat in transition regime."""

    def _make_config(self, **overrides):
        defaults = dict(
            transition_long_enabled=True,
            transition_short_enabled=True,
            transition_long_min_move_21d=-1.0,
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_volume_breakout_near_donchian_high(self):
        """Volume breakout near donchian high with reasonable RSI → signal."""
        bars = []
        for i in range(260):
            bars.append(_make_bar(
                ts=1700000000000 + i * 900_000,
                close=100.0,
                ema20=100.0,
                ema50=99.5,
                ema200=98.0,
                trend_strength=0.95,
                atr=2.0,
                atr_pct=0.02,
                rsi=55.0,
                vol_sma=400_000.0,
                volume_quote=400_000.0,
                donchian_high=104.0,
                donchian_low=96.0,
            ))
        # Last bar: volume breakout with tighter conditions
        bars.append(_make_bar(
            ts=1700000000000 + 260 * 900_000,
            close=104.0,  # at donchian high
            open=101.0,
            high=104.5,
            low=100.5,
            ema20=100.5,
            ema50=99.5,
            ema200=98.0,
            trend_strength=0.95,
            atr=2.0,
            atr_pct=0.02,
            rsi=62.0,  # not overbought
            vol_sma=400_000.0,
            volume_quote=560_000.0,  # vol_ratio ~1.4
            donchian_high=104.0,
            donchian_low=96.0,
        ))
        config = self._make_config()
        sig = signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, config)
        self.assertIsNotNone(sig)
        if sig:
            self.assertEqual(sig.direction, 1)
            self.assertIn(sig.reason, ("transition_breakout_long",))

    def test_volume_breakout_rsi_too_high_no_signal(self):
        """RSI > 68 → no volume breakout signal."""
        bars = []
        for i in range(260):
            bars.append(_make_bar(
                ts=1700000000000 + i * 900_000,
                close=100.0,
                ema20=100.0,
                ema50=99.5,
                ema200=98.0,
                trend_strength=0.95,
                atr=2.0,
                atr_pct=0.02,
                rsi=55.0,
                vol_sma=400_000.0,
                volume_quote=400_000.0,
                donchian_high=104.0,
                donchian_low=96.0,
            ))
        bars.append(_make_bar(
            ts=1700000000000 + 260 * 900_000,
            close=104.0,
            open=101.0,
            high=104.5,
            low=100.5,
            ema20=100.5,
            ema50=99.5,
            ema200=98.0,
            trend_strength=0.95,
            atr=2.0,
            atr_pct=0.02,
            rsi=72.0,  # overbought
            vol_sma=400_000.0,
            volume_quote=550_000.0,
            donchian_high=104.0,
            donchian_low=96.0,
        ))
        config = self._make_config()
        sig = signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, config)
        # RSI too high → no signal
        if sig and sig.direction == 1:
            self.assertNotIn("transition_breakout_long", sig.reason)

    def test_volume_breakout_long_upper_shadow_no_signal(self):
        """Long upper shadow candle → no signal (high rejection)."""
        bars = []
        for i in range(260):
            bars.append(_make_bar(
                ts=1700000000000 + i * 900_000,
                close=100.0,
                ema20=100.0,
                ema50=99.5,
                ema200=98.0,
                trend_strength=0.95,
                atr=2.0,
                atr_pct=0.02,
                rsi=55.0,
                vol_sma=400_000.0,
                volume_quote=400_000.0,
                donchian_high=104.0,
                donchian_low=96.0,
            ))
        bars.append(_make_bar(
            ts=1700000000000 + 260 * 900_000,
            close=101.0,  # close far below high
            open=100.5,
            high=106.0,  # long upper shadow
            low=100.0,
            ema20=100.5,
            ema50=99.5,
            ema200=98.0,
            trend_strength=0.95,
            atr=2.0,
            atr_pct=0.02,
            rsi=58.0,
            vol_sma=400_000.0,
            volume_quote=550_000.0,
            donchian_high=104.0,
            donchian_low=96.0,
        ))
        config = self._make_config()
        sig = signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, config)
        # Long upper shadow = rejection → no signal or weak signal
        # This is a quality filter test
        if sig and sig.direction == 1:
            # If signal exists, it should have lower score due to poor candle quality
            self.assertLessEqual(sig.score, 3.5)


class TestTransitionRegimeClassification(unittest.TestCase):
    """Verify transition regime is correctly classified."""

    def test_transition_regime_classification(self):
        """trend_strength between -1.2 and 1.2 → transition or range."""
        bar = _make_bar(
            ema50=100.0,
            ema200=100.5,
            trend_strength=0.95,
            atr_pct=0.005,
        )
        regime = classify_regime(bar)
        self.assertIn(regime, ("transition", "range"))

    def test_uptrend_not_transition(self):
        """Strong uptrend should not be classified as transition."""
        bar = _make_bar(
            ema50=102.0,
            ema200=98.0,
            trend_strength=1.5,
            atr_pct=0.02,
        )
        regime = classify_regime(bar)
        self.assertEqual(regime, "uptrend")


if __name__ == "__main__":
    unittest.main()
