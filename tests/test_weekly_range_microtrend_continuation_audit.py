from regime_validation_v2 import MEAN_REVERTING_RANGE
from weekly_range_microtrend_continuation_audit import (
    first_regime_exit,
    outcome_reasons,
    posthoc_sleeve_watchlist,
    ranked_priorities,
)


def test_ranked_priorities_prefers_largest_absolute_change():
    assert ranked_priorities({"A": 0.01, "B": -0.05, "C": 0.03}) == {
        "B": 0,
        "C": 1,
        "A": 2,
    }


def test_first_regime_exit_uses_first_later_non_range_label():
    labels = [(10, MEAN_REVERTING_RANGE), (20, MEAN_REVERTING_RANGE), (30, "uptrend"), (40, "downtrend")]
    assert first_regime_exit(labels, 10) == 30
    assert first_regime_exit(labels, 35) == 40


def test_outcome_reasons_requires_both_directional_sleeves():
    aggregate = {
        "accepted_positions": 120,
        "total_return_pct": 5.0,
        "max_drawdown_pct": 10.0,
        "top_positive_month_share": 0.20,
        "direction_attribution": {
            "weekly_range_microtrend_continuation_v1_long": {
                "accepted_positions": 60,
                "return_contribution_pct": 4.0,
            },
            "weekly_range_microtrend_continuation_v1_short": {
                "accepted_positions": 60,
                "return_contribution_pct": -1.0,
            },
        },
    }
    folds = {"a": {"total_return_pct": 1.0}, "b": {"total_return_pct": 1.0}, "c": {"total_return_pct": -1.0}}
    reasons = outcome_reasons(aggregate, folds)
    assert reasons == [
        "weekly_range_microtrend_continuation_v1_short return contribution -1.000000% <= 0%"
    ]


def test_posthoc_sleeve_watchlist_requires_two_positive_folds():
    aggregate = {
        "direction_attribution": {
            "weekly_range_microtrend_continuation_v1_long": {
                "accepted_positions": 60,
                "return_contribution_pct": 2.0,
            },
            "weekly_range_microtrend_continuation_v1_short": {
                "accepted_positions": 60,
                "return_contribution_pct": 3.0,
            },
        }
    }
    folds = {
        "a": {
            "direction_attribution": {
                "weekly_range_microtrend_continuation_v1_long": {"return_contribution_pct": 1.0},
                "weekly_range_microtrend_continuation_v1_short": {"return_contribution_pct": -1.0},
            }
        },
        "b": {
            "direction_attribution": {
                "weekly_range_microtrend_continuation_v1_long": {"return_contribution_pct": 1.0},
                "weekly_range_microtrend_continuation_v1_short": {"return_contribution_pct": 1.0},
            }
        },
        "c": {
            "direction_attribution": {
                "weekly_range_microtrend_continuation_v1_long": {"return_contribution_pct": -1.0},
                "weekly_range_microtrend_continuation_v1_short": {"return_contribution_pct": -1.0},
            }
        },
    }
    assert [item["component_id"] for item in posthoc_sleeve_watchlist(aggregate, folds)] == [
        "weekly_range_microtrend_continuation_v1_long"
    ]
