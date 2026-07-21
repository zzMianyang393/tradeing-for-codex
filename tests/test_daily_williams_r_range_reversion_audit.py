from daily_williams_r_range_reversion_audit import HIGH_THRESHOLD, LOOKBACK, LOW_THRESHOLD, RANGE_REGIME, verdict, williams_r
from market import Bar


def _bar(high, low, close):
    return Bar(0, "1970-01-01 00:00:00", close, high, low, close, 1.0)


def test_williams_r_uses_frozen_fourteen_bar_window():
    bars = [_bar(110.0, 90.0, 90.0) for _ in range(LOOKBACK)]
    assert williams_r(bars, LOOKBACK - 1) == -100.0
    assert (LOW_THRESHOLD, HIGH_THRESHOLD, RANGE_REGIME) == (-90.0, -10.0, "\u9707\u8361")


def test_verdict_keeps_small_sample_as_insufficient_evidence():
    stats = {"events": 14, "mean_pct": 1.0, "positive_return_month_concentration": 0.1}
    assert verdict(stats, stats)[0] == "insufficient_evidence"


def test_verdict_rejects_negative_mean_with_sufficient_events():
    stats = {"events": 15, "mean_pct": -0.1, "positive_return_month_concentration": 0.1}
    assert verdict(stats, stats)[0] == "historical_rejected"
