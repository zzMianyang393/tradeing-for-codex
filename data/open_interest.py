from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OpenInterest:
    symbol: str = ""
    oi: float = 0.0
    timestamp: int = 0


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_open_interest(exchange, symbol: str, days: int = 7) -> list[OpenInterest]:
    """Fetch historical open interest from OKX.

    Uses the /api/v5/public/open-interest-history endpoint.
    """
    oi_list = []
    try:
        data = exchange._request("GET", "/api/v5/public/open-interest-history", params={
            "instType": "SWAP",
            "instId": symbol,
            "period": "1H",  # 1-hour granularity
            "limit": str(min(days * 24, 100)),
        })
        for item in data.get("data", []):
            oi_list.append(OpenInterest(
                symbol=symbol,
                oi=float(item.get("oi", 0)),
                timestamp=int(item.get("ts", 0)),
            ))
    except Exception as e:
        logger.warning(f"Failed to fetch open interest for {symbol}: {e}")
    return oi_list


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def add_oi_features(bars: list[Any], oi_data: list[OpenInterest]) -> list[Any]:
    """Add open interest features to FeatureBar list.

    Features added:
    - open_interest: float (current OI)
    - oi_change_pct: float (OI change % over lookback)
    - oi_price_divergence: float (OI up + price down or vice versa)
    """
    if not bars:
        return bars

    # Set defaults for all bars
    for bar in bars:
        setattr(bar, "open_interest", 0.0)
        setattr(bar, "oi_change_pct", 0.0)
        setattr(bar, "oi_price_divergence", 0.0)

    if not oi_data:
        return bars

    # Sort OI data by timestamp
    sorted_oi = sorted(oi_data, key=lambda o: o.timestamp)

    # Match OI to bars by nearest timestamp
    oi_idx = 0
    lookback = 24  # hours for change calculation
    oi_values = [o.oi for o in sorted_oi]

    for bar in bars:
        bar_ts = getattr(bar, "ts", 0)

        # Find closest OI
        while oi_idx < len(sorted_oi) - 1 and sorted_oi[oi_idx + 1].timestamp <= bar_ts:
            oi_idx += 1

        current_oi = sorted_oi[oi_idx].oi if oi_idx < len(sorted_oi) else 0.0

        # Calculate OI change %
        lookback_idx = max(0, oi_idx - lookback)
        past_oi = sorted_oi[lookback_idx].oi if lookback_idx < len(sorted_oi) else current_oi
        oi_change_pct = (current_oi - past_oi) / past_oi if past_oi > 0 else 0.0

        # OI-price divergence
        # Positive = OI increasing while price decreasing (bearish)
        # Negative = OI decreasing while price increasing (bullish)
        price_change = getattr(bar, "close", 0) / getattr(bar, "open", 1) - 1.0 if getattr(bar, "open", 0) > 0 else 0.0
        divergence = oi_change_pct - price_change

        # Set attributes
        setattr(bar, "open_interest", current_oi)
        setattr(bar, "oi_change_pct", oi_change_pct)
        setattr(bar, "oi_price_divergence", divergence)

    return bars


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def save_oi_cache(oi_data: list[OpenInterest], path: Path) -> None:
    """Save open interest to JSON cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {"symbol": o.symbol, "oi": o.oi, "timestamp": o.timestamp}
        for o in oi_data
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_oi_cache(path: Path) -> list[OpenInterest]:
    """Load open interest from JSON cache."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [OpenInterest(**item) for item in data]
    except Exception as e:
        logger.warning(f"Failed to load OI cache: {e}")
        return []
