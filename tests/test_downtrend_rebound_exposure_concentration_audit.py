from __future__ import annotations

from downtrend_rebound_exposure_concentration_audit import (
    build_report,
    entry_cohorts,
    max_concurrent_positions,
    summarize_cohorts,
)


def _event(entry: int, exit_: int, symbol: str, value: float, split: str = "oos") -> dict:
    return {
        "entry_ts": entry,
        "exit_ts": exit_,
        "entry_timestamp_utc": f"2025-01-{entry:02d} 00:00:00",
        "signal_timestamp_utc": f"2025-01-{entry:02d} 00:00:00",
        "symbol": symbol,
        "split": split,
        "net_return_pct": value,
        "prior_downtrend_4h_streak": 2,
        "signal_rsi": 30.0,
        "event_time_inputs_complete": True,
    }


def test_entry_cohorts_equal_weight_same_timestamp():
    cohorts = entry_cohorts([_event(1, 5, "A", 10.0), _event(1, 4, "B", -2.0)])

    assert len(cohorts) == 1
    assert cohorts[0]["events"] == 2
    assert cohorts[0]["equal_weight_net_return_pct"] == 4.0


def test_max_concurrent_processes_exit_before_same_time_entry():
    events = [_event(1, 3, "A", 1.0), _event(3, 5, "B", 1.0)]

    assert max_concurrent_positions(events) == 1


def test_max_concurrent_counts_overlaps():
    events = [_event(1, 5, "A", 1.0), _event(2, 4, "B", 1.0)]

    assert max_concurrent_positions(events) == 2


def test_summarize_cohorts_reports_sum_not_account_return():
    cohorts = entry_cohorts([_event(1, 5, "A", 4.0), _event(2, 6, "B", -2.0)])

    summary = summarize_cohorts(cohorts)

    assert summary["cohort_net_sum_pct"] == 2.0
    assert summary["cohort_win_rate"] == 0.5


def test_build_report_keeps_safety_gates_closed():
    source = {"events": [_event(1, 5, "A", 4.0, "formation"), _event(2, 6, "B", 2.0)]}

    report = build_report(source)

    assert report["scope"] == "read_only_cohort_normalization_not_equity_curve"
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["eligible_for_paper"] is False
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False

