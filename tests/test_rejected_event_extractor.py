"""Tests for rejected_event_extractor.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rejected_event_extractor import (
    _classify_failure_reason,
    _extract_forward_return,
    _parse_month,
    extract_events_from_report,
    extract_from_funding_oi,
    extract_from_multi_coin_funding,
    extract_from_range_regime_funding,
    extract_generic_events,
    load_report,
)


class TestLoadReport:
    def test_valid(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('{"a": 1}', encoding="utf-8")
        assert load_report(p) == {"a": 1}

    def test_missing(self):
        assert load_report(Path("/nonexistent")) is None

    def test_bad_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")
        assert load_report(p) is None


class TestParseMonth:
    def test_from_day_string(self):
        assert _parse_month(None, "2024-10-27") == "2024-10"

    def test_from_timestamp(self):
        # 2024-11-06 00:00 UTC = 1730851200000
        assert _parse_month(1730851200000, None) == "2024-11"

    def test_unknown(self):
        assert _parse_month(None, None) == "unknown"


class TestExtractForwardReturn:
    def test_with_aggregate(self):
        event = {"aggregate": {"fwd_16bar": {"mean_pct": 1.0, "mean_net_pct": 0.86}}}
        gross, net = _extract_forward_return(event)
        assert gross == 1.0
        assert net == 0.86

    def test_with_forward_returns(self):
        event = {"forward_returns": {"fwd_16bar": {"mean_pct": -0.5, "mean_net_pct": -0.64}}}
        gross, net = _extract_forward_return(event)
        assert gross == -0.5
        assert net == -0.64

    def test_fallback_horizon(self):
        event = {"aggregate": {"fwd_96bar": {"mean_pct": 2.0, "mean_net_pct": 1.86}}}
        gross, net = _extract_forward_return(event, "fwd_16bar")
        assert gross == 2.0
        assert net == 1.86

    def test_empty(self):
        gross, net = _extract_forward_return({})
        assert gross is None
        assert net is None


class TestClassifyFailureReason:
    def test_severe_loss(self):
        event = {"aggregate": {"fwd_16bar": {"mean_pct": -1.0, "mean_net_pct": -1.14}}}
        assert _classify_failure_reason(event) == "severe_loss"

    def test_net_negative(self):
        event = {"aggregate": {"fwd_16bar": {"mean_pct": 0.1, "mean_net_pct": -0.04}}}
        assert _classify_failure_reason(event) == "net_negative"

    def test_unknown(self):
        assert _classify_failure_reason({}) == "unknown"


class TestExtractFromRangeRegimeFunding:
    def test_basic(self):
        report = {
            "overall": {
                "event_details": [
                    {
                        "funding_ts": 1730851200000,
                        "regime": "震荡",
                        "extreme_direction": "high",
                        "aggregate": {"fwd_16bar": {"mean_pct": -0.5, "mean_net_pct": -0.64}},
                    }
                ]
            }
        }
        events = extract_from_range_regime_funding(report, "test.json")
        assert len(events) == 1
        assert events[0]["strategy_id"] == "range_regime_funding_extreme"
        assert events[0]["regime"] == "震荡"
        assert events[0]["net_return"] == -0.64


class TestExtractFromFundingOi:
    def test_basic(self):
        report = {
            "formation": {
                "event_details": [
                    {
                        "event_day": "2024-11-06",
                        "scenario": "both_up",
                        "aggregate": {"fwd_16bar": {"mean_pct": 1.0, "mean_net_pct": 0.86}},
                    }
                ]
            }
        }
        events = extract_from_funding_oi(report, "test.json")
        assert len(events) == 1
        assert events[0]["strategy_id"] == "funding_oi_trend_confirmation"
        assert events[0]["month"] == "2024-11"


class TestExtractFromMultiCoinFunding:
    def test_basic(self):
        report = {
            "event_details": [
                {
                    "event_day": "2024-11-12",
                    "event_ts": 1731369600000,
                    "aggregate": {"fwd_16bar": {"mean_pct": 2.0, "mean_net_pct": 1.84}},
                }
            ]
        }
        events = extract_from_multi_coin_funding(report, "test.json")
        assert len(events) == 1
        assert events[0]["strategy_id"] == "multi_coin_funding_crowding"


class TestExtractGenericEvents:
    def test_event_details(self):
        report = {
            "event_details": [
                {
                    "event_day": "2024-10-01",
                    "scenario": "test",
                    "aggregate": {"fwd_16bar": {"mean_pct": 0.5, "mean_net_pct": 0.36}},
                }
            ]
        }
        events = extract_generic_events(report, "test.json", "my_strategy")
        assert len(events) == 1
        assert events[0]["strategy_id"] == "my_strategy"

    def test_empty(self):
        events = extract_generic_events({}, "test.json", "my_strategy")
        assert events == []


class TestSkippedSources:
    def test_no_event_details(self, tmp_path):
        """Reports without event_details should be skipped."""
        # Write a report without events
        report = {"n_events": 0, "forward_returns": {}}
        p = tmp_path / "no_events.json"
        p.write_text(json.dumps(report), encoding="utf-8")

        events = extract_generic_events(report, str(p), "test")
        assert events == []
