"""Funding-crowding candidate using audited external funding as a state proxy."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable

from market import FeatureBar
from strategy import Signal


EIGHT_HOURS_MS = 8 * 60 * 60 * 1000


def load_proxy_funding(path: Path) -> dict[int, float]:
    values: dict[int, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                values[int(row["timestamp_ms"]) // EIGHT_HOURS_MS] = float(row["funding_rate"])
            except (KeyError, TypeError, ValueError):
                continue
    return values


def build_funding_crowding_reversal_provider(
    funding_by_symbol: dict[str, dict[int, float]],
) -> Callable[[str, list[FeatureBar], int], Signal | None]:
    """Fade a 24h crowding extreme only at a completed funding interval.

    A three-interval cumulative funding payment of 0.12% plus a 3% same-way
    price move expresses a crowded directional trade.  The threshold is fixed
    before testing and intentionally far above ordinary funding noise.
    """
    def provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
        if idx < 96:
            return None
        bucket = bars[idx].ts // EIGHT_HOURS_MS
        rates = funding_by_symbol.get(symbol, {})
        if bucket not in rates:
            return None
        recent_buckets = (bucket - 2, bucket - 1, bucket)
        if any(item not in rates for item in recent_buckets):
            return None
        cumulative_funding = sum(rates[item] for item in recent_buckets)
        price_move = bars[idx].close / bars[idx - 96].close - 1.0 if bars[idx - 96].close else 0.0
        if cumulative_funding >= 0.0012 and price_move >= 0.03:
            return Signal(symbol, -1, 3.3, "candidate", "candidate_funding_crowding_reversal")
        if cumulative_funding <= -0.0012 and price_move <= -0.03:
            return Signal(symbol, 1, 3.3, "candidate", "candidate_funding_crowding_reversal")
        return None

    return provider
