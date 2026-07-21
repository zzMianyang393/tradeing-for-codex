"""Tests for no_trade_filter_research.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from no_trade_filter_research import (
    classify_failure_mode,
    extract_events_from_report,
    identify_filter_candidates,
    load_report,
)


# ── load_report ──────────────────────────────────────────────────────────────

class TestLoadReport:
    def test_valid_json(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            p = Path(tmp) / "test.json"
            p.write_text('{"key": "value"}', encoding="utf-8")
            assert load_report(p) == {"key": "value"}

    def test_missing_file(self):
        assert load_report(Path("/nonexistent/file.json")) is None

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("not json", encoding="utf-8")
            assert load_report(p) is None


# ── extract_events_from_report ───────────────────────────────────────────────

class TestExtractEvents:
    def test_event_details_format(self):
        report = {
            "event_details": [
                {"day": "2024-09-13", "scenario": "both_up", "aggregate": {"fwd_16bar": {"mean_net_pct": -0.5}}}
            ]
        }
        events = extract_events_from_report(report, "test")
        assert len(events) == 1
        assert events[0]["source"] == "test"
        assert events[0]["day"] == "2024-09-13"

    def test_formation_format(self):
        report = {
            "formation": {
                "event_details": [
                    {"event_day": "2024-10-01", "scenario": "both_down", "aggregate": {"fwd_16bar": {"mean_net_pct": 0.3}}}
                ]
            }
        }
        events = extract_events_from_report(report, "test")
        assert len(events) == 1

    def test_empty_report(self):
        events = extract_events_from_report({}, "test")
        assert events == []

    def test_no_events_key(self):
        report = {"some_other_key": 123}
        events = extract_events_from_report(report, "test")
        assert events == []


# ── classify_failure_mode ────────────────────────────────────────────────────

class TestClassifyFailure:
    def test_severe_loss(self):
        event = {"aggregate": {"fwd_16bar": {"mean_net_pct": -1.0, "win_rate": 0.3}}}
        modes = classify_failure_mode(event)
        assert "severe_loss" in modes

    def test_net_negative(self):
        event = {"aggregate": {"fwd_16bar": {"mean_net_pct": -0.2, "win_rate": 0.5}}}
        modes = classify_failure_mode(event)
        assert "net_negative" in modes

    def test_low_win_rate(self):
        event = {"aggregate": {"fwd_16bar": {"mean_net_pct": 0.1, "win_rate": 0.35}}}
        modes = classify_failure_mode(event)
        assert "low_win_rate" in modes

    def test_unknown(self):
        event = {"aggregate": {}}
        modes = classify_failure_mode(event)
        assert "unknown" in modes


# ── identify_filter_candidates ───────────────────────────────────────────────

class TestIdentifyFilters:
    def test_month_concentration(self):
        """Months with >70% failure rate should be flagged."""
        events = [
            {"day": f"2024-10-{i:02d}", "scenario": "both_up", "aggregate": {"fwd_16bar": {"mean_net_pct": -1.0, "win_rate": 0.3}}}
            for i in range(1, 11)
        ]
        candidates = identify_filter_candidates(events)
        month_candidates = [c for c in candidates if c["filter_type"] == "month_blackout"]
        assert len(month_candidates) >= 1
        assert month_candidates[0]["value"] == "2024-10"

    def test_scenario_blackout(self):
        """Scenarios with >60% failure rate and >=5 events should be flagged."""
        events = [
            {"day": f"2024-0{i}-01", "scenario": "both_down", "aggregate": {"fwd_16bar": {"mean_net_pct": -1.0, "win_rate": 0.3}}}
            for i in range(1, 7)
        ]
        candidates = identify_filter_candidates(events)
        scenario_candidates = [c for c in candidates if c["filter_type"] == "scenario_blackout"]
        assert len(scenario_candidates) >= 1

    def test_no_candidates_for_good_events(self):
        """Events with positive returns should not generate filter candidates."""
        events = [
            {"day": f"2024-0{i}-01", "scenario": "both_up", "aggregate": {"fwd_16bar": {"mean_net_pct": 0.5, "win_rate": 0.7}}}
            for i in range(1, 7)
        ]
        candidates = identify_filter_candidates(events)
        assert len(candidates) == 0

    def test_short_hold_penalty(self):
        """Short-holding events with >60% failure should be flagged."""
        events = [
            {
                "day": f"2024-0{i}-01",
                "scenario": "test",
                "aggregate": {
                    "fwd_1bar": {"mean_net_pct": -0.3, "win_rate": 0.3},
                    "fwd_4bar": {"mean_net_pct": -0.3, "win_rate": 0.3},
                },
            }
            for i in range(1, 12)
        ]
        candidates = identify_filter_candidates(events)
        short_candidates = [c for c in candidates if c["filter_type"] == "short_hold_penalty"]
        assert len(short_candidates) >= 1

    def test_empty_events(self):
        candidates = identify_filter_candidates([])
        assert candidates == []
