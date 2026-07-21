from market import FeatureBar
from low_volatility_drift_breakout_audit import breakout_direction


def feature(close: float, lower: float, upper: float) -> FeatureBar:
    return FeatureBar(0, "", close, close, close, close, 0.0, bb_lower=lower, bb_upper=upper)


def test_breakout_direction_detects_upper_cross():
    assert breakout_direction(feature(99.0, 90.0, 100.0), feature(101.0, 90.0, 100.0)) == "long"


def test_breakout_direction_detects_lower_cross():
    assert breakout_direction(feature(91.0, 90.0, 100.0), feature(89.0, 90.0, 100.0)) == "short"


def test_breakout_direction_ignores_inside_band():
    assert breakout_direction(feature(95.0, 90.0, 100.0), feature(96.0, 90.0, 100.0)) is None

