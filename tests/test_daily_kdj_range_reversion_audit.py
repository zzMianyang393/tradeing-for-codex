from daily_kdj_range_reversion_audit import LOOKBACK, RULE_ID, kdj_values, verdict
from market import Bar


def _bar(index: int, high: float, low: float, close: float) -> Bar:
    return Bar(index * 86_400_000, "", close, high, low, close, 1.0)


def test_kdj_is_unavailable_before_full_completed_window():
    bars = [_bar(index, 11 + index, 9 + index, 10 + index) for index in range(LOOKBACK)]
    k_values, d_values = kdj_values(bars)

    assert all(value is None for value in k_values[:LOOKBACK - 1])
    assert all(value is None for value in d_values[:LOOKBACK - 1])
    assert k_values[LOOKBACK - 1] is not None
    assert d_values[LOOKBACK - 1] is not None


def test_kdj_rule_id_is_frozen():
    assert RULE_ID == "daily_kdj_range_reversion_v1"


def test_verdict_requires_positive_and_nonconcentrated_oos():
    formation = {"events": 16, "mean_pct": 1.0, "positive_return_month_concentration": 0.2}
    oos = {"events": 16, "mean_pct": -1.0, "positive_return_month_concentration": 0.2}

    assert verdict(formation, oos)[0] == "historical_rejected"


def test_verdict_marks_small_sample_insufficient():
    stats = {"events": 14, "mean_pct": 1.0, "positive_return_month_concentration": 0.2}

    assert verdict(stats, stats)[0] == "insufficient_evidence"
