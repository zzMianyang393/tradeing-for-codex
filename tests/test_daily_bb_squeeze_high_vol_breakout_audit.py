from daily_bb_squeeze_high_vol_breakout_audit import BB_PERIOD, RULE_ID, bollinger_widths, percentile, verdict
from market import Bar


def _bar(index: int, close: float) -> Bar:
    return Bar(index * 86_400_000, "", close, close + 1.0, close - 1.0, close, 1.0)


def test_bollinger_values_require_completed_window():
    middles, uppers, lowers = bollinger_widths([_bar(index, 100.0 + index) for index in range(BB_PERIOD)])

    assert middles[BB_PERIOD - 2] is None
    assert middles[BB_PERIOD - 1] is not None
    assert uppers[BB_PERIOD - 1] > middles[BB_PERIOD - 1] > lowers[BB_PERIOD - 1]


def test_percentile_is_left_discrete_and_deterministic():
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.20) == 1.0


def test_rule_id_is_frozen():
    assert RULE_ID == "daily_bb_squeeze_high_vol_breakout_v1"


def test_verdict_marks_small_sample_insufficient():
    stats = {"events": 14, "mean_pct": 1.0, "positive_return_month_concentration": 0.1}
    assert verdict(stats, stats)[0] == "insufficient_evidence"
