"""Tests for funding_oi_trend_confirmation_audit.py (corrected timing)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from funding_oi_trend_confirmation_audit import (
    available_funding_at_1600,
    coin_contribution,
    compute_event_returns,
    compute_signals,
    load_funding_by_day,
    load_ohlcv,
    load_oi,
    month_concentration,
    summarise,
    verdict,
)


# ── available_funding_at_1600 ────────────────────────────────────────────────

class TestAvailableFunding:
    def test_filters_out_1600_settlement(self):
        """Only 00:00 and 08:00 should be returned (ts < 16:00)."""
        day = "2025-01-08"
        # 00:00, 08:00, 16:00 UTC
        funding = {day: [
            {"ts": 1736294400000, "rate": 0.0001},  # 00:00
            {"ts": 1736323200000, "rate": 0.0002},  # 08:00
            {"ts": 1736352000000, "rate": 0.0003},  # 16:00
        ]}
        result = available_funding_at_1600(day, funding)
        assert result is not None
        assert len(result) == 2
        assert all(r["ts"] < 1736352000000 for r in result)

    def test_returns_none_if_fewer_than_2(self):
        day = "2025-01-08"
        funding = {day: [{"ts": 1736294400000, "rate": 0.0001}]}
        assert available_funding_at_1600(day, funding) is None

    def test_returns_none_if_missing(self):
        assert available_funding_at_1600("2025-01-08", {}) is None


# ── compute_signals ──────────────────────────────────────────────────────────

def _make_multi_coin_data(scenario: str):
    """Build 5-coin test data for a given scenario."""
    symbols = [f"COIN{i}-USDT-SWAP" for i in range(5)]
    funding: dict[str, dict[str, list[dict]]] = {}
    oi: dict[str, dict[str, dict]] = {}
    for sym in symbols:
        if scenario == "both_up":
            f1_rate, f2_rate, oi1, oi2 = 0.0001, 0.0002, 1e9, 2e9
        elif scenario == "both_down":
            f1_rate, f2_rate, oi1, oi2 = 0.0002, 0.0001, 2e9, 1e9
        else:  # mixed
            f1_rate, f2_rate, oi1, oi2 = 0.0001, 0.0002, 2e9, 1e9
        funding[sym] = {
            "2025-01-01": [
                {"ts": 1735689600000, "rate": f1_rate},
                {"ts": 1735718400000, "rate": f1_rate},
            ],
            "2025-01-02": [
                {"ts": 1735776000000, "rate": f2_rate},
                {"ts": 1735804800000, "rate": f2_rate},
            ],
        }
        oi[sym] = {
            "2025-01-01": {"ts": 1735747200000, "oi_usd": oi1},
            "2025-01-02": {"ts": 1735833600000, "oi_usd": oi2},
        }
    return symbols, funding, oi


class TestComputeSignals:
    def test_both_up_detected(self):
        symbols, funding, oi = _make_multi_coin_data("both_up")
        signals = compute_signals(symbols, funding, oi, ["2025-01-01", "2025-01-02"])
        assert len(signals) == 1
        assert signals[0]["scenario"] == "both_up"
        assert signals[0]["both_up_pct"] == 1.0

    def test_both_down_detected(self):
        symbols, funding, oi = _make_multi_coin_data("both_down")
        signals = compute_signals(symbols, funding, oi, ["2025-01-01", "2025-01-02"])
        assert len(signals) == 1
        assert signals[0]["scenario"] == "both_down"

    def test_mixed_scenario(self):
        symbols, funding, oi = _make_multi_coin_data("mixed")
        signals = compute_signals(symbols, funding, oi, ["2025-01-01", "2025-01-02"])
        assert len(signals) == 1
        assert signals[0]["scenario"] == "none"  # mixed, below threshold

    def test_signal_ts_is_1615(self):
        symbols, funding, oi = _make_multi_coin_data("both_up")
        signals = compute_signals(symbols, funding, oi, ["2025-01-01", "2025-01-02"])
        # 2025-01-02 00:00 UTC = 1735776000000
        # 16:15 UTC = 1735776000000 + 16*3600*1000 + 15*60*1000
        expected = 1735776000000 + 58500000
        assert signals[0]["signal_ts"] == expected


# ── verdict ──────────────────────────────────────────────────────────────────

class TestVerdict:
    def test_passes_when_all_criteria_met(self):
        summary = {
            "fwd_16bar": {"n_events": 12, "avg_net_mean_pct": 0.5, "avg_win_rate": 0.60}
        }
        mc = {"max_month_pct": 0.20}
        cc = {"max_contribution_pct": 0.15}
        v, reasons = verdict(summary, mc, cc)
        assert v == "通过形成期"
        assert reasons == []

    def test_fails_on_low_win_rate(self):
        summary = {
            "fwd_16bar": {"n_events": 12, "avg_net_mean_pct": 0.5, "avg_win_rate": 0.40}
        }
        mc = {"max_month_pct": 0.20}
        cc = {"max_contribution_pct": 0.15}
        v, reasons = verdict(summary, mc, cc)
        assert v == "淘汰"
        assert any("win rate" in r for r in reasons)

    def test_fails_on_negative_mean(self):
        summary = {
            "fwd_16bar": {"n_events": 12, "avg_net_mean_pct": -0.1, "avg_win_rate": 0.60}
        }
        mc = {"max_month_pct": 0.20}
        cc = {"max_contribution_pct": 0.15}
        v, reasons = verdict(summary, mc, cc)
        assert v == "淘汰"
        assert any("net mean" in r for r in reasons)

    def test_fails_on_month_concentration(self):
        summary = {
            "fwd_16bar": {"n_events": 12, "avg_net_mean_pct": 0.5, "avg_win_rate": 0.60}
        }
        mc = {"max_month_pct": 0.35}
        cc = {"max_contribution_pct": 0.15}
        v, reasons = verdict(summary, mc, cc)
        assert v == "淘汰"
        assert any("month" in r for r in reasons)

    def test_fails_on_coin_concentration(self):
        summary = {
            "fwd_16bar": {"n_events": 12, "avg_net_mean_pct": 0.5, "avg_win_rate": 0.60}
        }
        mc = {"max_month_pct": 0.20}
        cc = {"max_contribution_pct": 0.50}
        v, reasons = verdict(summary, mc, cc)
        assert v == "淘汰"
        assert any("coin" in r for r in reasons)


# ── month_concentration ──────────────────────────────────────────────────────

class TestMonthConcentration:
    def test_basic(self):
        events = [
            {"event_day": "2024-09-13"},
            {"event_day": "2024-09-19"},
            {"event_day": "2024-10-27"},
        ]
        mc = month_concentration(events)
        assert mc["distribution"]["2024-09"] == 2
        assert mc["distribution"]["2024-10"] == 1
        assert mc["max_month_pct"] == round(2 / 3, 3)


# ── coin_contribution ────────────────────────────────────────────────────────

class TestCoinContribution:
    def test_basic(self):
        events = [
            {
                "per_coin_net": {
                    "BTC": {"fwd_96bar": 1.0},
                    "ETH": {"fwd_96bar": -0.5},
                },
            },
            {
                "per_coin_net": {
                    "BTC": {"fwd_96bar": 2.0},
                    "ETH": {"fwd_96bar": 0.3},
                },
            },
        ]
        cc = coin_contribution(events)
        assert cc["per_coin"]["BTC"]["n_events"] == 2
        assert cc["per_coin"]["BTC"]["mean_net_pct"] == 1.5
        assert cc["per_coin"]["ETH"]["n_events"] == 2


# ── integration with real data ───────────────────────────────────────────────

class TestRealData:
    def test_load_funding(self):
        data = load_funding_by_day("BTC-USDT-SWAP", 1704067200000, 1735689600000)
        if not data:
            pytest.skip("No BTC funding data")
        assert len(data) > 100
        # each day should have 3 settlements
        sample_day = sorted(data.keys())[10]
        assert len(data[sample_day]) == 3

    def test_load_oi(self):
        data = load_oi("BTC-USDT-SWAP", 1704067200000, 1735689600000)
        if not data:
            pytest.skip("No BTC OI data")
        assert len(data) > 100

    def test_load_ohlcv(self):
        data = load_ohlcv("BTC", 1704067200000, 1735689600000)
        if not data:
            pytest.skip("No BTC OHLCV data")
        assert len(data) > 1000
