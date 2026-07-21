from __future__ import annotations

from market import Bar
from daily_atr_expansion_breakout_audit import RULE_ID, breakout_direction, verdict


def bar(index: int, high: float, low: float, close: float) -> Bar:
    return Bar(index * 900_000, "", close, high, low, close, 1.0)


def test_breakout_requires_prior_channel_and_atr_expansion():
    daily = [bar(index, 11, 9, 10) for index in range(20)]
    daily.append(bar(20, 14, 9, 13))
    assert breakout_direction(daily, 20, 2.0) == "long"
    assert breakout_direction(daily, 20, 4.0) is None


def test_breakout_does_not_use_current_bar_in_prior_channel():
    daily = [bar(index, 11, 9, 10) for index in range(20)]
    daily.append(bar(20, 14, 9, 11))
    assert breakout_direction(daily, 20, 2.0) is None


def test_rule_and_gates_are_frozen():
    assert RULE_ID == "daily_atr_expansion_breakout_v1"
    stats = {"events": 15, "mean_pct": 1.0, "positive_return_month_concentration": 0.2}
    assert verdict(stats, stats)[0] == "historical_research_candidate"
