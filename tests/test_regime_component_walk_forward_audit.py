from __future__ import annotations

from market import Bar
from regime_component_walk_forward_audit import (
    candidate_reasons,
    fold_events,
    leave_one_sleeve_out_diagnostics,
    realized_pnl_by_component,
    summarize_shared_capital_combo,
    supertrend_direction,
    wilder_atr,
)


def bar(index: int, close: float = 100.0) -> Bar:
    return Bar(
        ts=index * 60_000,
        time=f"t{index}",
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume_quote=1.0,
    )


def test_wilder_atr_has_no_values_before_full_period():
    values = wilder_atr([bar(index) for index in range(5)], 3)
    assert values[:2] == [None, None]
    assert values[2:] == [2.0, 2.0, 2.0]


def test_supertrend_outputs_one_direction_per_bar():
    bars = [bar(index, 100.0 + index) for index in range(20)]
    directions, atr = supertrend_direction(bars, period=3, multiplier=2.0)
    assert len(directions) == len(bars)
    assert len(atr) == len(bars)
    assert set(directions[2:]).issubset({-1, 1})


def test_fold_events_omits_positions_crossing_fold_end():
    events = [
        {"entry_ts": 1_704_067_200_000, "exit_ts": 1_704_153_600_000},
        {"entry_ts": 1_719_705_600_000, "exit_ts": 1_719_792_000_000},
    ]
    assert fold_events(events, "2024-01-01", "2024-06-30") == [events[0]]


def passing_result():
    return {
        "accepted_positions": 35,
        "total_return_pct": 3.0,
        "max_drawdown_pct": 10.0,
        "top_positive_month_share": 0.20,
    }


def test_candidate_screen_can_pass_all_frozen_thresholds():
    folds = {str(index): {"total_return_pct": 1.0 if index < 3 else -0.1} for index in range(5)}
    assert candidate_reasons(passing_result(), folds) == []


def test_candidate_screen_reports_all_threshold_families():
    result = passing_result()
    result.update(accepted_positions=29, total_return_pct=0.0, max_drawdown_pct=20.1, top_positive_month_share=0.251)
    folds = {str(index): {"total_return_pct": 1.0 if index < 2 else -0.1} for index in range(5)}
    reasons = candidate_reasons(result, folds)
    assert len(reasons) == 5


def test_shared_capital_combo_keeps_a_frozen_equal_position_rule(monkeypatch):
    expected = passing_result()
    calls = []

    def fake_run(events, _price_maps):
        calls.append(events)
        return dict(expected)

    monkeypatch.setattr("regime_component_walk_forward_audit.run_portfolio", fake_run)
    events = [{"component_id": "a", "entry_ts": 1, "exit_ts": 2}, {"component_id": "b", "entry_ts": 3, "exit_ts": 4}]
    result = summarize_shared_capital_combo(events, {})
    assert result["generated_events"] == 2
    assert result["event_counts_by_component"] == {"a": 1, "b": 1}
    assert result["portfolio_rules"]["position_fraction"] == 0.20
    assert result["portfolio_rules"]["component_weights"] == "no sleeve weights; each accepted position uses the same fixed fraction"
    assert result["status"] == "historical_walk_forward_candidate"
    assert len(calls) == 6


def test_realized_pnl_attribution_groups_closed_positions_by_component():
    aggregate = {"closed_positions": [
        {"component_id": "a", "realized_pnl": 12.5},
        {"component_id": "a", "realized_pnl": -2.0},
        {"component_id": "b", "realized_pnl": -4.0},
    ]}
    assert realized_pnl_by_component(aggregate) == {"a": 10.5, "b": -4.0}


def test_leave_one_out_is_fixed_diagnostic_not_candidate_selection(monkeypatch):
    def fake_summary(events, _price_maps):
        return {
            "aggregate": passing_result(),
            "positive_fold_count": 3,
            "candidate_reasons": [],
        }

    monkeypatch.setattr("regime_component_walk_forward_audit.summarize_shared_capital_combo", fake_summary)
    events = [{"component_id": component} for component in (
        "uptrend_donchian_55_20_long", "uptrend_supertrend_4h_long",
        "range_bb_reversion_4h", "range_rsi_reversion_4h",
    )]
    diagnostics = leave_one_sleeve_out_diagnostics(events, {})
    assert len(diagnostics) == 4
    for excluded, result in diagnostics.items():
        assert result["excluded_component"] == excluded
        assert excluded not in result["remaining_components"]
        assert result["diagnostic_only"] is True
        assert result["not_a_candidate"] is True
