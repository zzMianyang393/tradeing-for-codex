"""Tests for regime_label_coverage_audit.py."""

from __future__ import annotations

import pytest

from regime_label_coverage_audit import (
    compute_coverage,
    check_btc_alt_consistency,
    resample_4h,
    label_4h_bars,
)


class TestResample4h:
    def test_basic(self):
        bars = [{"ts": i * 900000, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10} for i in range(16)]
        result = resample_4h(bars)
        assert len(result) == 1
        assert result[0]["volume"] == 160

    def test_multiple_buckets(self):
        bars = [{"ts": i * 900000, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10} for i in range(32)]
        result = resample_4h(bars)
        assert len(result) == 2


class TestComputeCoverage:
    def test_empty_labels(self):
        result = compute_coverage([], 0, 1000)
        assert result["n_labels"] == 0
        assert result["status"] == "insufficient"

    def test_basic_coverage(self):
        labels = [(i * 3600000, "震荡") for i in range(100)]
        result = compute_coverage(labels, 0, 100 * 3600000)
        assert result["n_labels"] == 100
        assert result["coverage_rate"] > 0


class TestBtcAltConsistency:
    def test_identical_labels(self):
        btc = [(1000, "趋势上行"), (2000, "震荡")]
        alt = {"ETH": [(1000, "趋势上行"), (2000, "震荡")]}
        result = check_btc_alt_consistency(btc, alt)
        assert result["ETH"]["agreement_rate"] == 1.0

    def test_divergent_labels(self):
        btc = [(1000, "趋势上行"), (2000, "震荡")]
        alt = {"ETH": [(1000, "趋势下行"), (2000, "趋势下行")]}
        result = check_btc_alt_consistency(btc, alt)
        assert result["ETH"]["agreement_rate"] == 0.0
