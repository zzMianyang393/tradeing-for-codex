"""Tests for range_regime_funding_extreme_audit.py."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from range_regime_funding_extreme_audit import (
    _atr,
    _ema,
    label_4h_bars,
    load_funding,
    load_ohlcv_15m,
    regime_at,
    resample_4h,
    rolling_percentile,
    verdict,
    summarise_events,
)


# ── rolling_percentile ────────────────────────────────────────────────────────

class TestRollingPercentile:
    def test_no_look_ahead(self):
        """Values at position i must only use data from positions < i."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = rolling_percentile(values, window=5, pct=0.9)
        # First 5 should be None (not enough window)
        for i in range(5):
            assert result[i] is None, f"Position {i} should be None"
        # Position 5: window is [1,2,3,4,5], 90th percentile = 5
        assert result[5] == 5.0
        # Position 6: window is [2,3,4,5,6], 90th percentile = 6
        assert result[6] == 6.0

    def test_constant_values(self):
        values = [5.0] * 20
        result = rolling_percentile(values, window=10, pct=0.95)
        assert result[10] == 5.0
        assert result[19] == 5.0

    def test_empty(self):
        result = rolling_percentile([], window=5, pct=0.9)
        assert result == []


# ── regime labeling ──────────────────────────────────────────────────────────

class TestRegimeLabeling:
    def test_resample_4h(self):
        # Create 16 x 15m bars = 1 x 4h bar
        bars = [
            {"ts": i * 900000, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100}
            for i in range(16)
        ]
        result = resample_4h(bars)
        assert len(result) == 1
        assert result[0]["open"] == 100
        assert result[0]["volume"] == 1600

    def test_label_4h_bars_insufficient(self):
        bars = [{"ts": i * FOUR_H_MS, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100}
                for i in range(100)]
        assert label_4h_bars(bars) == []

    def test_regime_at_before_any_label(self):
        labels = [(1000, "震荡"), (2000, "趋势上行")]
        assert regime_at(labels, 500) is None

    def test_regime_at_exact_match(self):
        labels = [(1000, "震荡"), (2000, "趋势上行")]
        assert regime_at(labels, 1000) == "震荡"

    def test_regime_at_between_labels(self):
        labels = [(1000, "震荡"), (2000, "趋势上行")]
        assert regime_at(labels, 1500) == "震荡"


FOUR_H_MS = 4 * 3600 * 1000


# ── EMA / ATR ────────────────────────────────────────────────────────────────

class TestEma:
    def test_first_value(self):
        result = _ema([10, 20, 30], 2)
        assert result[0] == 10

    def test_length(self):
        result = _ema([1, 2, 3, 4, 5], 3)
        assert len(result) == 5


class TestAtr:
    def test_length(self):
        h = [105, 110, 108, 112]
        l = [95, 100, 98, 102]
        c = [100, 105, 103, 107]
        result = _atr(h, l, c, period=2)
        assert len(result) == 4


# ── verdict ──────────────────────────────────────────────────────────────────

class TestVerdict:
    def test_pass(self):
        summary = {
            "n_events": 20,
            "max_month_pct": 0.20,
            "forward_returns": {
                "fwd_16bar": {"mean_net_pct": 0.5, "win_rate": 0.60}
            }
        }
        v, reasons = verdict(summary)
        assert v == "通过形成期"
        assert reasons == []

    def test_fail_few_events(self):
        summary = {"n_events": 5, "max_month_pct": 0.20, "forward_returns": {}}
        v, reasons = verdict(summary)
        assert v == "淘汰"
        assert any("events" in r for r in reasons)

    def test_fail_negative_mean(self):
        summary = {
            "n_events": 20,
            "max_month_pct": 0.20,
            "forward_returns": {"fwd_16bar": {"mean_net_pct": -0.1, "win_rate": 0.60}}
        }
        v, reasons = verdict(summary)
        assert v == "淘汰"
        assert any("net mean" in r for r in reasons)

    def test_fail_low_win_rate(self):
        summary = {
            "n_events": 20,
            "max_month_pct": 0.20,
            "forward_returns": {"fwd_16bar": {"mean_net_pct": 0.5, "win_rate": 0.40}}
        }
        v, reasons = verdict(summary)
        assert v == "淘汰"
        assert any("win rate" in r for r in reasons)

    def test_fail_month_concentration(self):
        summary = {
            "n_events": 20,
            "max_month_pct": 0.35,
            "forward_returns": {"fwd_16bar": {"mean_net_pct": 0.5, "win_rate": 0.60}}
        }
        v, reasons = verdict(summary)
        assert v == "淘汰"
        assert any("month" in r for r in reasons)


# ── summarise_events ─────────────────────────────────────────────────────────

class TestSummariseEvents:
    def test_empty(self):
        assert summarise_events([]) == {"n_events": 0}

    def test_basic(self):
        events = [
            {
                "funding_ts": 1704067200000,
                "extreme_direction": "high",
                "forward_returns": {"fwd_16bar": {"ret_pct": 1.0, "net_ret_pct": 0.86}},
            },
            {
                "funding_ts": 1704153600000,
                "extreme_direction": "low",
                "forward_returns": {"fwd_16bar": {"ret_pct": -0.5, "net_ret_pct": -0.64}},
            },
        ]
        result = summarise_events(events)
        assert result["n_events"] == 2
        assert result["direction_breakdown"]["high"] == 1
        assert result["direction_breakdown"]["low"] == 1


# ── integration with real data ───────────────────────────────────────────────

class TestRealData:
    def test_load_ohlcv(self):
        data = load_ohlcv_15m("BTC")
        if not data:
            pytest.skip("No BTC OHLCV data")
        assert len(data) > 1000

    def test_load_funding(self):
        data = load_funding("BTC-USDT-SWAP")
        if not data:
            pytest.skip("No BTC funding data")
        assert len(data) > 100
