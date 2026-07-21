"""Post-hoc v2 regime vocabulary that refines only the residual range label."""

from __future__ import annotations

from directional_regime_conditioned_audit import RANGE_COMPATIBLE_REGIMES
from market import Bar, add_features, resample_minutes
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars


EFFICIENCY_LOOKBACK = 6
MEAN_REVERTING_RANGE = "mean_reverting_range_v2"
LOW_VOLATILITY_DRIFT = "low_volatility_drift_v2"


def efficiency_ratio(bars: list[Bar], index: int, lookback: int = EFFICIENCY_LOOKBACK) -> float | None:
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if index < lookback:
        return None
    displacement = abs(bars[index].close - bars[index - lookback].close)
    path = sum(abs(bars[item].close - bars[item - 1].close) for item in range(index - lookback + 1, index + 1))
    return displacement / path if path > 0 else 0.0


def label_completed_4h_bars_v2(bars_15m: list[Bar]) -> list[tuple[int, str]]:
    raw_4h = resample_minutes(bars_15m, 240)
    featured = add_features(raw_4h)
    original = label_completed_4h_bars(bars_15m)
    refined: list[tuple[int, str]] = []
    for index, ((available_ts, label), _bar) in enumerate(zip(original, featured)):
        if label not in RANGE_COMPATIBLE_REGIMES:
            refined.append((available_ts, label))
            continue
        ratio = efficiency_ratio(raw_4h, index)
        refined.append(
            (
                available_ts,
                MEAN_REVERTING_RANGE if ratio is not None and ratio <= 0.30 else LOW_VOLATILITY_DRIFT,
            )
        )
    return refined

