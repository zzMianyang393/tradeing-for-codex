"""Tests for ML signal generator."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from ml_signal import (
    FEATURE_COLUMNS,
    MLSignalConfig,
    extract_features,
    prepare_dataset,
)


def _make_bar(**kwargs):
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


class TestExtractFeatures(unittest.TestCase):
    """Test feature extraction from FeatureBar."""

    def test_returns_all_features(self):
        bar = _make_bar()
        features = extract_features(bar)
        for col in FEATURE_COLUMNS:
            self.assertIn(col, features)

    def test_volume_ratio(self):
        bar = _make_bar(volume_quote=800_000.0, vol_sma=400_000.0)
        features = extract_features(bar)
        self.assertAlmostEqual(features["volume_ratio"], 2.0)

    def test_close_to_ema20(self):
        bar = _make_bar(close=110.0, ema20=100.0)
        features = extract_features(bar)
        self.assertAlmostEqual(features["close_to_ema20"], 0.1)

    def test_bb_position_mid(self):
        bar = _make_bar(close=100.0, bb_upper=110.0, bb_lower=90.0)
        features = extract_features(bar)
        self.assertAlmostEqual(features["bb_position"], 0.5)

    def test_candle_body_pct(self):
        bar = _make_bar(open=100.0, close=102.0)
        features = extract_features(bar)
        self.assertAlmostEqual(features["candle_body_pct"], 0.02, places=2)


class TestPrepareDataset(unittest.TestCase):
    """Test dataset preparation."""

    def test_shapes(self):
        bars = [_make_bar(close=100.0 + i * 0.1) for i in range(200)]
        X, y = prepare_dataset(bars, forward_bars=10, profit_threshold_pct=0.001)
        self.assertEqual(X.shape[0], y.shape[0])
        self.assertEqual(X.shape[1], len(FEATURE_COLUMNS))

    def test_labels_binary(self):
        bars = [_make_bar(close=100.0 + i * 0.1) for i in range(200)]
        _, y = prepare_dataset(bars, forward_bars=10, profit_threshold_pct=0.001)
        unique = set(y.tolist())
        self.assertTrue(unique.issubset({0, 1}))

    def test_insufficient_data(self):
        bars = [_make_bar() for _ in range(5)]
        X, y = prepare_dataset(bars, forward_bars=10)
        self.assertEqual(len(X), 0)


class TestMLSignalConfig(unittest.TestCase):
    """Test config defaults."""

    def test_defaults(self):
        cfg = MLSignalConfig()
        self.assertEqual(cfg.train_days, 180)
        self.assertEqual(cfg.test_days, 30)
        self.assertEqual(cfg.forward_bars, 96)
        self.assertEqual(cfg.min_score, 0.6)


if __name__ == "__main__":
    unittest.main()
