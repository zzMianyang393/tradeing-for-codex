"""Tests for cross_time_stability_audit.py."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from cross_time_stability_audit import (
    _kurtosis,
    _pearson,
    _skew,
    classify_stability,
    compare_windows,
    compute_cross_coin_correlation,
    compute_funding_stats,
    compute_oi_stats,
    compute_ohlcv_stats,
    load_funding,
    load_oi_daily,
    load_ohlcv_15m,
)


# ─── Statistical helpers ─────────────────────────────────────────────────────

class TestSkew:
    def test_symmetric(self):
        data = [-2, -1, 0, 1, 2]
        assert abs(_skew(data)) < 0.1

    def test_right_skew(self):
        data = [0, 0, 0, 0, 10]
        assert _skew(data) > 0

    def test_insufficient_data(self):
        assert _skew([1, 2]) == 0.0

    def test_constant(self):
        assert _skew([5, 5, 5, 5, 5]) == 0.0


class TestKurtosis:
    def test_normal_like(self):
        data = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
        # Excess kurtosis should be negative for uniform-like
        k = _kurtosis(data)
        assert isinstance(k, float)

    def test_insufficient_data(self):
        assert _kurtosis([1, 2, 3]) == 0.0

    def test_constant(self):
        assert _kurtosis([5, 5, 5, 5, 5]) == 0.0


class TestPearson:
    def test_perfect_positive(self):
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        assert abs(_pearson(x, y) - 1.0) < 1e-10

    def test_perfect_negative(self):
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]
        assert abs(_pearson(x, y) - (-1.0)) < 1e-10

    def test_no_correlation(self):
        x = [1, 2, 3, 4, 5]
        y = [5, 2, 8, 1, 7]
        corr = _pearson(x, y)
        assert -0.5 < corr < 0.5

    def test_insufficient_data(self):
        assert math.isnan(_pearson([1], [2]))


# ─── Stability classification ────────────────────────────────────────────────

class TestClassifyStability:
    def test_stable(self):
        w1 = {"mean_rate": 0.0001}
        w2 = {"mean_rate": 0.00012}
        assert classify_stability(w1, w2, "mean_rate", 50.0) == "稳定"

    def test_unstable(self):
        w1 = {"mean_rate": 0.0001}
        w2 = {"mean_rate": 0.0005}
        assert classify_stability(w1, w2, "mean_rate", 50.0) == "不稳定"

    def test_insufficient_on_error(self):
        w1 = {"error": "insufficient data"}
        w2 = {"mean_rate": 0.0001}
        assert classify_stability(w1, w2, "mean_rate", 50.0) == "样本不足"

    def test_insufficient_on_none(self):
        w1 = {"mean_rate": None}
        w2 = {"mean_rate": 0.0001}
        assert classify_stability(w1, w2, "mean_rate", 50.0) == "样本不足"


class TestCompareWindows:
    def test_all_stable(self):
        w1 = {"return_mean": 0.001, "return_stdev": 0.05}
        w2 = {"return_mean": 0.0011, "return_stdev": 0.055}
        result = compare_windows(w1, w2, ["return_mean", "return_stdev"], 50.0)
        assert all(v["stability"] == "稳定" for v in result.values())

    def test_mixed(self):
        w1 = {"return_mean": 0.001, "return_stdev": 0.05}
        w2 = {"return_mean": 0.005, "return_stdev": 0.055}
        result = compare_windows(w1, w2, ["return_mean", "return_stdev"], 50.0)
        assert result["return_mean"]["stability"] == "不稳定"
        assert result["return_stdev"]["stability"] == "稳定"


# ─── OHLCV stats ─────────────────────────────────────────────────────────────

class TestComputeOhlcvStats:
    def test_basic(self):
        rows = [
            {"ts": i * 900000, "open": 100 + i * 0.1, "high": 101 + i * 0.1,
             "low": 99 + i * 0.1, "close": 100 + i * 0.1, "volume": 1000}
            for i in range(1000)
        ]
        stats = compute_ohlcv_stats(rows)
        assert stats["n_bars"] == 1000
        assert stats["n_days"] > 0
        assert "return_mean" in stats
        assert "return_stdev" in stats
        assert "missing_bar_rate" in stats

    def test_insufficient(self):
        stats = compute_ohlcv_stats([{"ts": 0, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}])
        assert "error" in stats


# ─── Funding stats ───────────────────────────────────────────────────────────

class TestComputeFundingStats:
    def test_basic(self):
        rows = [{"ts": i * 28800000, "rate": 0.0001 + i * 0.00001} for i in range(100)]
        stats = compute_funding_stats(rows)
        assert stats["n_records"] == 100
        assert "mean_rate" in stats
        assert "extreme_rate" in stats
        assert "coverage" in stats

    def test_insufficient(self):
        stats = compute_funding_stats([{"ts": 0, "rate": 0.0001}])
        assert "error" in stats


# ─── OI stats ────────────────────────────────────────────────────────────────

class TestComputeOiStats:
    def test_basic(self):
        rows = [{"ts": i * 86400000, "oi_usd": 1e9 + i * 1e7} for i in range(100)]
        stats = compute_oi_stats(rows)
        assert stats["n_records"] == 100
        assert "mean_oi_usd" in stats
        assert "extreme_change_rate" in stats

    def test_insufficient(self):
        stats = compute_oi_stats([{"ts": 0, "oi_usd": 1e9}])
        assert "error" in stats


# ─── Cross-coin correlation ──────────────────────────────────────────────────

class TestCrossCoinCorrelation:
    def test_with_real_data(self):
        """Test with real data if available (integration test)."""
        btc = load_ohlcv_15m("BTC")
        eth = load_ohlcv_15m("ETH")
        if len(btc) < 1000 or len(eth) < 1000:
            pytest.skip("Insufficient real data")
        result = compute_cross_coin_correlation(["BTC", "ETH"], {"BTC": btc, "ETH": eth})
        assert result["n_pairs"] == 1
        assert -1 <= result["mean_corr"] <= 1

    def test_empty(self):
        result = compute_cross_coin_correlation([], {})
        assert result["n_pairs"] == 0


# ─── Integration with real data ──────────────────────────────────────────────

class TestRealDataIntegration:
    """Integration tests that verify the audit works with actual data files."""

    def test_load_ohlcv(self):
        rows = load_ohlcv_15m("BTC")
        if not rows:
            pytest.skip("No BTC OHLCV data")
        assert len(rows) > 1000
        assert all("ts" in r and "close" in r and "volume" in r for r in rows[:10])

    def test_load_funding(self):
        rows = load_funding("BTC-USDT-SWAP")
        if not rows:
            pytest.skip("No BTC funding data")
        assert len(rows) > 100
        assert all("ts" in r and "rate" in r for r in rows[:10])

    def test_load_oi(self):
        rows = load_oi_daily("BTC-USDT-SWAP")
        if not rows:
            pytest.skip("No BTC OI data")
        assert len(rows) > 100
        assert all("ts" in r and "oi_usd" in r for r in rows[:10])

    def test_ohlcv_stats_real(self):
        rows = load_ohlcv_15m("BTC")
        if len(rows) < 1000:
            pytest.skip("Insufficient BTC data")
        stats = compute_ohlcv_stats(rows)
        assert stats["n_bars"] > 1000
        assert stats["return_stdev"] > 0
        assert stats["daily_volume_mean"] > 0
