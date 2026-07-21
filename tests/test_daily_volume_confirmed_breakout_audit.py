from market import Bar
from daily_volume_confirmed_breakout_audit import RULE_ID, breakout_direction, verdict


def bar(i, high, low, close, volume): return Bar(i * 900_000, "", close, high, low, close, volume)


def test_breakout_requires_both_channel_and_volume_confirmation():
    bars = [bar(i, 11, 9, 10, 10) for i in range(20)] + [bar(20, 14, 9, 13, 30)]
    assert breakout_direction(bars, 20) == "long"
    bars[-1] = bar(20, 14, 9, 13, 20)
    assert breakout_direction(bars, 20) is None


def test_breakout_excludes_current_bar_from_reference_windows():
    bars = [bar(i, 11, 9, 10, 10) for i in range(20)] + [bar(20, 14, 9, 11, 30)]
    assert breakout_direction(bars, 20) is None


def test_frozen_rule_and_full_split_gate():
    assert RULE_ID == "daily_volume_confirmed_breakout_v1"
    good = {"events": 15, "mean_pct": 1.0, "positive_return_month_concentration": 0.2}
    assert verdict(good, good)[0] == "historical_research_candidate"
