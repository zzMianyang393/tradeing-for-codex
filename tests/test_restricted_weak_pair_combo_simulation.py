from restricted_weak_pair_combo_simulation import combo_reasons, posthoc_risk_adjusted_watchlist, summarize_result


def passing_result() -> dict:
    return {
        "accepted_positions": 60,
        "total_return_pct": 10.0,
        "max_drawdown_pct": 5.0,
        "top_positive_month_share": 0.20,
        "component_attribution": {
            "left": {"accepted_positions": 30, "return_contribution_pct": 4.0},
            "right": {"accepted_positions": 30, "return_contribution_pct": 6.0},
        },
    }


def test_combo_reasons_accepts_passing_shared_capital_result():
    aggregate = passing_result()
    folds = {str(i): {"total_return_pct": 1.0 if i < 3 else -1.0} for i in range(5)}
    standalone = {"left": {"max_drawdown_pct": 6.0}, "right": {"max_drawdown_pct": 4.0}}
    assert combo_reasons(aggregate, folds, standalone, ("left", "right")) == []


def test_combo_reasons_requires_positive_component_contributions():
    aggregate = passing_result()
    aggregate["component_attribution"]["right"]["return_contribution_pct"] = -1.0
    folds = {str(i): {"total_return_pct": 1.0} for i in range(5)}
    standalone = {"left": {"max_drawdown_pct": 6.0}, "right": {"max_drawdown_pct": 4.0}}
    reasons = combo_reasons(aggregate, folds, standalone, ("left", "right"))
    assert any("right return contribution" in reason for reason in reasons)


def test_summarize_result_drops_large_equity_and_position_arrays():
    result = {
        "candidate_events": 1,
        "accepted_positions": 1,
        "capacity_rejected_events": 0,
        "total_return_pct": 1.0,
        "max_drawdown_pct": 0.5,
        "realized_win_rate": 1.0,
        "average_gross_exposure": 0.1,
        "peak_gross_exposure": 0.1,
        "capital_turnover": 0.1,
        "top_positive_month_share": 1.0,
        "component_attribution": {},
        "equity_curve": [1],
        "closed_positions": [1],
    }
    summary = summarize_result(result)
    assert "equity_curve" not in summary
    assert "closed_positions" not in summary


def test_posthoc_watchlist_does_not_override_non_drawdown_failures():
    aggregate = passing_result()
    result = posthoc_risk_adjusted_watchlist(
        aggregate,
        ["accepted positions 40 < 50"],
        {"left": {"max_drawdown_pct": 6.0}, "right": {"max_drawdown_pct": 4.0}},
        ("left", "right"),
        4,
    )
    assert result["retained_as_posthoc_risk_adjusted_watchlist"] is False
