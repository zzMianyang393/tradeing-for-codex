"""Tests for regime_label_transition_audit.py."""

from __future__ import annotations

import pytest

from regime_label_transition_audit import analyze_transitions, verify_timing_correctness


class TestAnalyzeTransitions:
    def test_no_transitions(self):
        labels = [{"bar_ts": i * 1000, "available_at": i * 1000 + 14400000, "label": "震荡"} for i in range(10)]
        result = analyze_transitions(labels)
        assert result["n_transitions"] == 0
        assert result["flicker_rate"] == 0

    def test_one_transition(self):
        labels = [{"bar_ts": i * 1000, "available_at": i * 1000 + 14400000, "label": "震荡"} for i in range(5)]
        labels += [{"bar_ts": i * 1000, "available_at": i * 1000 + 14400000, "label": "趋势上行"} for i in range(5, 10)]
        result = analyze_transitions(labels)
        assert result["n_transitions"] == 1

    def test_flicker_detection(self):
        labels = [
            {"bar_ts": 0, "available_at": 14400000, "label": "震荡"},
            {"bar_ts": 1000, "available_at": 15400000, "label": "趋势上行"},  # flicker
            {"bar_ts": 2000, "available_at": 16400000, "label": "震荡"},
        ]
        result = analyze_transitions(labels)
        assert result["flicker_count"] >= 1


class TestVerifyTimingCorrectness:
    def test_valid_timing(self):
        labels = [{"bar_ts": 100000, "available_at": 114400000, "label": "震荡"}]
        result = verify_timing_correctness(labels)
        assert result["status"] == "valid"
        assert result["n_violations"] == 0

    def test_invalid_timing(self):
        labels = [{"bar_ts": 100000, "available_at": 50000, "label": "震荡"}]  # available before bar
        result = verify_timing_correctness(labels)
        assert result["status"] == "invalid_for_activation"
        assert result["n_violations"] == 1
