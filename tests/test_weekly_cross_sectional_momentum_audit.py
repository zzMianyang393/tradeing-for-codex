from weekly_cross_sectional_momentum_audit import outcome_reasons, posthoc_sleeve_watchlist, select_ranked


def test_select_ranked_returns_three_strongest_and_weakest():
    scores = {f"S{i}": float(i) for i in range(10)}
    longs, shorts = select_ranked(scores)
    assert longs == ["S9", "S8", "S7"]
    assert shorts == ["S0", "S1", "S2"]


def test_outcome_reasons_accepts_balanced_long_short_result():
    aggregate = {
        "accepted_positions": 240,
        "total_return_pct": 5.0,
        "max_drawdown_pct": 10.0,
        "top_positive_month_share": 0.2,
        "sleeve_attribution": {
            "weekly_cross_sectional_momentum_v1_long": {
                "accepted_positions": 120,
                "return_contribution_pct": 2.0,
            },
            "weekly_cross_sectional_momentum_v1_short": {
                "accepted_positions": 120,
                "return_contribution_pct": 3.0,
            },
        },
    }
    folds = {"a": {"total_return_pct": 1.0}, "b": {"total_return_pct": 1.0}, "c": {"total_return_pct": -1.0}}
    assert outcome_reasons(aggregate, folds) == []


def test_posthoc_sleeve_watchlist_requires_positive_sleeve_in_two_folds():
    aggregate = {
        "sleeve_attribution": {
            "weekly_cross_sectional_momentum_v1_long": {
                "accepted_positions": 120,
                "return_contribution_pct": -5.0,
            },
            "weekly_cross_sectional_momentum_v1_short": {
                "accepted_positions": 120,
                "return_contribution_pct": 6.0,
            },
        }
    }
    folds = {
        "a": {"sleeve_attribution": {"weekly_cross_sectional_momentum_v1_short": {"return_contribution_pct": 1.0}}},
        "b": {"sleeve_attribution": {"weekly_cross_sectional_momentum_v1_short": {"return_contribution_pct": 1.0}}},
        "c": {"sleeve_attribution": {"weekly_cross_sectional_momentum_v1_short": {"return_contribution_pct": -1.0}}},
    }
    assert [item["component_id"] for item in posthoc_sleeve_watchlist(aggregate, folds)] == [
        "weekly_cross_sectional_momentum_v1_short"
    ]
