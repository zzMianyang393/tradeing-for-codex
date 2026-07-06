from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FundingRate:
    symbol: str = ""
    funding_rate: float = 0.0
    next_funding_rate: float = 0.0
    funding_time: str = ""
    timestamp: int = 0


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_funding_rate(exchange, symbol: str, days: int = 7) -> list[FundingRate]:
    """Fetch historical funding rates from OKX.

    Uses the /api/v5/public/funding-rate-history endpoint.
    Returns up to 100 most recent funding rates (OKX limit).
    """
    rates = []
    try:
        data = exchange._request("GET", "/api/v5/public/funding-rate-history", params={
            "instId": symbol,
            "limit": str(min(days * 3, 100)),  # ~3 per day for swap
        })
        for item in data.get("data", []):
            rates.append(FundingRate(
                symbol=symbol,
                funding_rate=float(item.get("fundingRate", 0)),
                next_funding_rate=float(item.get("nextFundingRate", 0)),
                funding_time=item.get("fundingTime", ""),
                timestamp=int(item.get("fundingTime", 0)),
            ))
    except Exception as e:
        logger.warning(f"Failed to fetch funding rate for {symbol}: {e}")
    return rates


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def add_funding_features(bars: list[Any], funding_rates: list[FundingRate]) -> list[Any]:
    """Add funding rate features to FeatureBar list.

    Features added:
    - funding_rate: float (current funding rate)
    - funding_rate_ma: float (7-period moving average)
    - funding_rate_zscore: float (z-score of current rate vs MA)
    """
    if not bars:
        return bars

    # Set defaults for all bars
    for bar in bars:
        setattr(bar, "funding_rate", 0.0)
        setattr(bar, "funding_rate_ma", 0.0)
        setattr(bar, "funding_rate_zscore", 0.0)

    if not funding_rates:
        return bars

    # Build timestamp -> funding rate lookup
    rate_by_ts: dict[int, float] = {}
    for fr in funding_rates:
        if fr.timestamp > 0:
            rate_by_ts[fr.timestamp] = fr.funding_rate

    # Sort rates by timestamp
    sorted_rates = sorted(funding_rates, key=lambda r: r.timestamp)
    rate_values = [r.funding_rate for r in sorted_rates]

    # Calculate rolling statistics
    window = 7
    ma = _rolling_mean(rate_values, window)
    std = _rolling_std(rate_values, window)

    # Match funding rates to bars by nearest timestamp
    rate_idx = 0
    for bar in bars:
        bar_ts = getattr(bar, "ts", 0)

        # Find closest funding rate
        while rate_idx < len(sorted_rates) - 1 and sorted_rates[rate_idx + 1].timestamp <= bar_ts:
            rate_idx += 1

        if rate_idx < len(sorted_rates):
            current_rate = sorted_rates[rate_idx].funding_rate
        else:
            current_rate = 0.0

        # Calculate z-score
        if rate_idx < len(ma) and std[rate_idx] > 0:
            zscore = (current_rate - ma[rate_idx]) / std[rate_idx]
        else:
            zscore = 0.0

        # Set attributes
        setattr(bar, "funding_rate", current_rate)
        setattr(bar, "funding_rate_ma", ma[rate_idx] if rate_idx < len(ma) else 0.0)
        setattr(bar, "funding_rate_zscore", zscore)

    return bars


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rolling_mean(values: list[float], window: int) -> list[float]:
    """Calculate rolling mean."""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        result.append(sum(values[start:i + 1]) / (i - start + 1))
    return result


def _rolling_std(values: list[float], window: int) -> list[float]:
    """Calculate rolling standard deviation."""
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        subset = values[start:i + 1]
        mean = sum(subset) / len(subset)
        variance = sum((x - mean) ** 2 for x in subset) / len(subset)
        result.append(math.sqrt(variance))
    return result


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def save_funding_cache(rates: list[FundingRate], path: Path) -> None:
    """Save funding rates to JSON cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "symbol": r.symbol,
            "funding_rate": r.funding_rate,
            "next_funding_rate": r.next_funding_rate,
            "funding_time": r.funding_time,
            "timestamp": r.timestamp,
        }
        for r in rates
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_funding_cache(path: Path) -> list[FundingRate]:
    """Load funding rates from JSON cache."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [FundingRate(**item) for item in data]
    except Exception as e:
        logger.warning(f"Failed to load funding cache: {e}")
        return []
