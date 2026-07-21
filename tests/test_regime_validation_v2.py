from market import Bar
from regime_validation_v2 import efficiency_ratio


def make_bar(index: int, close: float) -> Bar:
    return Bar(index, str(index), close, close, close, close, 1.0)


def test_efficiency_ratio_is_one_for_monotonic_path():
    bars = [make_bar(index, float(index)) for index in range(7)]
    assert efficiency_ratio(bars, 6) == 1.0


def test_efficiency_ratio_is_zero_for_round_trip_path():
    closes = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
    bars = [make_bar(index, close) for index, close in enumerate(closes)]
    assert efficiency_ratio(bars, 6) == 0.0


def test_efficiency_ratio_requires_full_lookback():
    bars = [make_bar(index, float(index)) for index in range(3)]
    assert efficiency_ratio(bars, 2, lookback=6) is None

