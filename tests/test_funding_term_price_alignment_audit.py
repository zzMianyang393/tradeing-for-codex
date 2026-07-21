from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME
from funding_term_price_alignment_audit import (
    first_incompatible_regime_exit,
    grouped_attribution,
    normalized_extremeness,
    outcome_reasons,
    posthoc_sleeve_watchlist,
)
from regime_validation_v2 import LOW_VOLATILITY_DRIFT


def test_first_incompatible_regime_exit_preserves_direction_compatible_labels():
    labels = [(10, LONG_COMPATIBLE_REGIME), (20, LOW_VOLATILITY_DRIFT), (30, "趋势下行")]
    assert first_incompatible_regime_exit(labels, 10, "long") == 30


def test_normalized_extremeness_uses_relevant_threshold():
    state = {
        "state": "high_positive",
        "current": 0.0003,
        "high_threshold": 0.0002,
        "low_threshold": -0.0001,
    }
    assert round(normalized_extremeness(state), 6) == 0.5


def test_outcome_reasons_requires_each_direction_to_contribute():
    aggregate = {
        "accepted_positions": 150,
        "total_return_pct": 5.0,
        "max_drawdown_pct": 10.0,
        "top_positive_month_share": 0.2,
        "direction_attribution": {
            "funding_term_price_alignment_v1_long": {
                "accepted_positions": 80,
                "return_contribution_pct": 4.0,
            },
            "funding_term_price_alignment_v1_short": {
                "accepted_positions": 70,
                "return_contribution_pct": -1.0,
            },
        },
    }
    folds = {"a": {"total_return_pct": 1.0}, "b": {"total_return_pct": 1.0}, "c": {"total_return_pct": -1.0}}
    assert outcome_reasons(aggregate, folds) == [
        "funding_term_price_alignment_v1_short return contribution -1.000000% <= 0%"
    ]


def test_grouped_attribution_recovers_regime_from_source_event():
    events = [
        {
            "symbol": "BTC",
            "entry_ts": 10,
            "component_id": "c",
            "entry_regime": "趋势下行",
        }
    ]
    result = {
        "initial_equity": 100_000.0,
        "closed_positions": [
            {"symbol": "BTC", "entry_ts": 10, "component_id": "c", "realized_pnl": 100.0}
        ],
    }
    assert grouped_attribution(result, events, "entry_regime")["趋势下行"]["accepted_positions"] == 1


def test_posthoc_watchlist_does_not_count_tiny_positive_folds():
    component = "funding_term_price_alignment_v1_short"
    aggregate = {
        "direction_attribution": {
            "funding_term_price_alignment_v1_long": {
                "accepted_positions": 100,
                "return_contribution_pct": -1.0,
            },
            component: {"accepted_positions": 43, "return_contribution_pct": 20.0},
        }
    }
    folds = {
        "a": {"direction_attribution": {component: {"accepted_positions": 37, "return_contribution_pct": 10.0}}},
        "b": {"direction_attribution": {component: {"accepted_positions": 5, "return_contribution_pct": 2.0}}},
        "c": {"direction_attribution": {component: {"accepted_positions": 1, "return_contribution_pct": 1.0}}},
    }
    assert posthoc_sleeve_watchlist(aggregate, folds) == []
