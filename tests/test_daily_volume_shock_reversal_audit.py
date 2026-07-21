from daily_volume_shock_reversal_audit import late_constant_symbols, outcome_reasons, posthoc_direction_watchlist


def test_late_constant_symbols_intersects_three_late_folds():
    universe = {
        "eligible_symbols_by_fold": {
            "2025-H1": ["BTC", "ETH"],
            "2025-H2": ["BTC", "SOL"],
            "2026-H1": ["BTC", "ADA"],
        }
    }
    assert late_constant_symbols(universe) == ["BTC"]


def test_outcome_reasons_accepts_balanced_three_fold_result():
    aggregate = {
        "accepted_positions": 60,
        "total_return_pct": 5.0,
        "max_drawdown_pct": 10.0,
        "top_positive_month_share": 0.20,
        "direction_attribution": {
            "daily_volume_shock_reversal_v1_long": {
                "accepted_positions": 30,
                "return_contribution_pct": 2.0,
            },
            "daily_volume_shock_reversal_v1_short": {
                "accepted_positions": 30,
                "return_contribution_pct": 3.0,
            },
        },
    }
    folds = {
        "a": {"total_return_pct": 1.0},
        "b": {"total_return_pct": 1.0},
        "c": {"total_return_pct": -1.0},
    }
    assert outcome_reasons(aggregate, folds) == []


def test_posthoc_direction_watchlist_requires_two_positive_folds():
    aggregate = {
        "direction_attribution": {
            "daily_volume_shock_reversal_v1_long": {
                "accepted_positions": 30,
                "return_contribution_pct": -1.0,
            },
            "daily_volume_shock_reversal_v1_short": {
                "accepted_positions": 40,
                "return_contribution_pct": 3.0,
            },
        }
    }
    folds = {
        "a": {"direction_attribution": {"daily_volume_shock_reversal_v1_short": {"return_contribution_pct": 1.0}}},
        "b": {"direction_attribution": {"daily_volume_shock_reversal_v1_short": {"return_contribution_pct": 1.0}}},
        "c": {"direction_attribution": {"daily_volume_shock_reversal_v1_short": {"return_contribution_pct": -1.0}}},
    }
    watchlist = posthoc_direction_watchlist(aggregate, folds)
    assert [item["component_id"] for item in watchlist] == ["daily_volume_shock_reversal_v1_short"]
