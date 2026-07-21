from __future__ import annotations

from market import Bar
from daily_parabolic_sar_trend_audit import RULE_ID, sar_directions, verdict


def bar(index: int, high: float, low: float, close: float) -> Bar:
    return Bar(index * 900_000, "", close, high, low, close, 1.0)


def test_sar_identifies_reversal_without_future_bars():
    bars = [bar(0, 11, 9, 10), bar(1, 12, 10, 11), bar(2, 13, 11, 12), bar(3, 12, 7, 8)]
    directions = sar_directions(bars)
    assert directions[:3] == [1, 1, 1]
    assert directions[3] == -1


def test_sar_rule_id_is_frozen():
    assert RULE_ID == "daily_parabolic_sar_trend_v1"


def test_verdict_requires_both_splits_to_clear_all_gates():
    formation = {"events": 16, "mean_pct": 1.0, "positive_return_month_concentration": 0.2}
    oos = {"events": 16, "mean_pct": -1.0, "positive_return_month_concentration": 0.2}
    assert verdict(formation, oos)[0] == "historical_rejected"
