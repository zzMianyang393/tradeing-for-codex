from high_positive_funding_long_risk_filter_audit import event_net_outcome_pct, filter_reasons


def test_event_net_outcome_prefers_frozen_event_value():
    assert event_net_outcome_pct({"net_return_pct": 1.2, "realized_return_pct": 1.0}) == 1.2
    assert event_net_outcome_pct({"realized_return_pct": -0.5}) == -0.5


def test_filter_reasons_passes_stable_adverse_high_funding_state():
    high = {"events": 40, "mean_net_outcome_pct": -0.5}
    other = {"events": 100, "mean_net_outcome_pct": 0.1}
    folds = {
        "a": {"events": 15, "mean_net_outcome_pct": -0.4},
        "b": {"events": 15, "mean_net_outcome_pct": -0.3},
        "c": {"events": 10, "mean_net_outcome_pct": 0.1},
    }
    assert filter_reasons(high, other, folds) == []


def test_filter_reasons_rejects_tiny_negative_folds():
    high = {"events": 40, "mean_net_outcome_pct": -0.5}
    other = {"events": 100, "mean_net_outcome_pct": 0.1}
    folds = {
        "a": {"events": 9, "mean_net_outcome_pct": -1.0},
        "b": {"events": 9, "mean_net_outcome_pct": -1.0},
        "c": {"events": 22, "mean_net_outcome_pct": 0.1},
    }
    assert filter_reasons(high, other, folds) == ["qualified negative folds 0/3 < 2/3"]
