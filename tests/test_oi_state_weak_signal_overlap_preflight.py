from oi_deleveraging_filter_audit import OiRow, PriceBar
from oi_state_weak_signal_overlap_preflight import overlaps_state, trailing_notionals_at_oi_times


def test_trailing_notionals_use_only_prior_24_hours():
    oi_rows = [OiRow("BTC", 100, "t", 1000.0)]
    bars = [
        PriceBar(1, 1.0, 2.0, 3.0),
        PriceBar(99, 1.0, 4.0, 5.0),
        PriceBar(101, 1.0, 100.0, 100.0),
    ]
    assert trailing_notionals_at_oi_times(oi_rows, bars) == [26.0]


def test_overlap_includes_state_boundaries():
    intervals = [(10, 20), (30, 40)]
    assert overlaps_state(10, intervals) is True
    assert overlaps_state(20, intervals) is True
    assert overlaps_state(25, intervals) is False
