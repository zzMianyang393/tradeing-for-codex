from __future__ import annotations

from downtrend_rebound_event_time_filter_audit import (
    advancement_reasons,
    render_markdown,
    select_hypotheses,
    split_summary,
    strict_prior_regime_streak,
)


def _event(streak: int, rsi: float, split: str = "oos", value: float = 1.0) -> dict:
    return {
        "split": split,
        "net_return_pct": value,
        "signal_timestamp_utc": "2025-02-01 00:00:00" if split == "oos" else "2024-02-01 00:00:00",
        "prior_downtrend_4h_streak": streak,
        "signal_rsi": rsi,
        "event_time_inputs_complete": True,
    }


def test_strict_prior_streak_excludes_label_available_exactly_at_entry():
    labels = [(100, "趋势下行"), (200, "趋势下行"), (300, "趋势下行")]

    assert strict_prior_regime_streak(labels, 300) == 2


def test_strict_prior_streak_stops_at_different_regime():
    labels = [(100, "趋势下行"), (200, "震荡"), (300, "趋势下行")]

    assert strict_prior_regime_streak(labels, 400) == 1


def test_select_hypotheses_uses_frozen_boundaries():
    events = [_event(1, 24.9), _event(6, 25.0), _event(7, 34.9)]

    selected = select_hypotheses(events)

    assert len(selected["H0_downtrend_rsi_baseline"]) == 3
    assert len(selected["F1_prior_downtrend_streak_1_to_6"]) == 2
    assert len(selected["F2_prior_downtrend_streak_ge_7"]) == 1
    assert len(selected["F3_signal_rsi_below_25"]) == 1
    assert len(selected["F4_signal_rsi_25_to_35"]) == 2


def test_incomplete_event_time_inputs_are_excluded():
    incomplete = _event(4, 0.0)
    incomplete["event_time_inputs_complete"] = False

    selected = select_hypotheses([incomplete])

    assert all(not events for events in selected.values())


def test_split_summary_reports_concentration_and_november_exclusion():
    events = [
        _event(2, 20.0, "formation", 3.0),
        {**_event(2, 20.0, "formation", 9.0), "signal_timestamp_utc": "2024-11-01 00:00:00"},
        _event(2, 20.0, "oos", -1.0),
    ]

    summary = split_summary(events)

    assert summary["formation"]["events"] == 2
    assert summary["formation"]["mean_excluding_2024_11_pct"] == 3.0
    assert summary["oos"]["net_sum_pct"] == -1.0


def test_advancement_reasons_keep_small_oos_sample_blocked():
    summary = split_summary([_event(2, 20.0, "formation", 1.0), _event(2, 20.0, "oos", 1.0)])

    reasons = advancement_reasons(summary)

    assert any("OOS events" in reason for reason in reasons)


def test_render_markdown_preserves_safety_status():
    summary = split_summary([_event(2, 20.0, "formation"), _event(2, 20.0, "oos")])
    report = {
        "research_id": "downtrend_rebound_event_time_filter_v1",
        "scope": "read_only_event_time_diagnostic_not_executable_strategy",
        "source_event_count": 2,
        "downtrend_event_count": 2,
        "complete_event_time_input_count": 2,
        "strict_timing_rule": "strictly earlier",
        "hypothesis_reviews": {
            name: {"summary": summary, "advancement_reasons": ["blocked"], "passes_current_screen": False}
            for name in (
                "H0_downtrend_rsi_baseline",
                "F1_prior_downtrend_streak_1_to_6",
                "F2_prior_downtrend_streak_ge_7",
                "F3_signal_rsi_below_25",
                "F4_signal_rsi_25_to_35",
            )
        },
    }

    document = render_markdown(report)

    assert "eligible_for_paper = false" in document
    assert "ready_for_combo_backtest = false" in document
