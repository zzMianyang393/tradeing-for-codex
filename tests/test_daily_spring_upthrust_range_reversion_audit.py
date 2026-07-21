from daily_spring_upthrust_range_reversion_audit import RULE_ID, signal_direction, verdict
from market import Bar


def _bar(high: float, low: float, close: float) -> Bar:
    return Bar(0, "", close, high, low, close, 1.0)


def test_spring_requires_break_below_then_close_back_inside_channel():
    assert signal_direction(_bar(101, 89, 98), 110, 90) == "long"
    assert signal_direction(_bar(101, 89, 93), 110, 90) is None


def test_upthrust_requires_break_above_then_close_back_inside_channel():
    assert signal_direction(_bar(111, 99, 102), 110, 90) == "short"
    assert signal_direction(_bar(111, 99, 108), 110, 90) is None


def test_rule_id_is_frozen():
    assert RULE_ID == "daily_spring_upthrust_range_reversion_v1"


def test_small_samples_are_insufficient():
    stats = {"events": 14, "mean_pct": 1.0, "positive_return_month_concentration": 0.1}
    assert verdict(stats, stats)[0] == "insufficient_evidence"


def test_negative_oos_rejects_with_enough_events():
    formation = {"events": 15, "mean_pct": 1.0, "positive_return_month_concentration": 0.1}
    oos = {"events": 15, "mean_pct": -1.0, "positive_return_month_concentration": 0.1}
    assert verdict(formation, oos)[0] == "historical_rejected"
