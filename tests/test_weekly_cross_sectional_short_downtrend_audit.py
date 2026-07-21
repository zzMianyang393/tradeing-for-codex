from weekly_cross_sectional_short_downtrend_audit import DOWN_TREND, RULE_ID, split, verdict
from regime_component_walk_forward_audit import parse_day


def test_rule_id_and_regime_are_frozen():
    assert RULE_ID == "weekly_cross_sectional_momentum_v1_short_downtrend"
    assert DOWN_TREND == "趋势下行"


def test_split_uses_fixed_historical_windows():
    assert split(parse_day("2024-08-05")) == "formation"
    assert split(parse_day("2025-02-03")) == "oos"
    assert split(parse_day("2025-07-11")) is None


def test_verdict_requires_both_splits_and_low_concentration():
    formation = {"events": 16, "mean_pct": 1.0, "positive_return_month_concentration": 0.2}
    oos = {"events": 16, "mean_pct": -1.0, "positive_return_month_concentration": 0.2}
    assert verdict(formation, oos)[0] == "historical_rejected"


def test_small_oos_is_insufficient():
    stats = {"events": 14, "mean_pct": 1.0, "positive_return_month_concentration": 0.2}
    assert verdict(stats, stats)[0] == "insufficient_evidence"
