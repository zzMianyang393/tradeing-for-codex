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
class TradesFlow:
    symbol: str = ""
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    timestamp: int = 0


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_trades_flow(exchange, symbol: str, days: int = 7) -> list[TradesFlow]:
    """Fetch recent trades and calculate buy/sell flow.

    Uses the /api/v5/market/trades endpoint to get recent trades,
    then aggregates into flow buckets.
    """
    try:
        # Get recent trades (max 500 per request)
        data = exchange._request("GET", "/api/v5/market/trades", params={
            "instId": symbol,
            "limit": "500",
        })

        trades = data.get("data", [])

        # Aggregate by time bucket (1-minute buckets)
        buckets: dict[int, TradesFlow] = {}
        for t in trades:
            ts = int(t.get("ts", 0))
            minute_ts = (ts // 60000) * 60000  # Round to minute

            side = t.get("side", "")
            qty = float(t.get("sz", 0))

            if minute_ts not in buckets:
                buckets[minute_ts] = TradesFlow(
                    symbol=symbol,
                    timestamp=minute_ts,
                )

            bucket = buckets[minute_ts]
            if side == "buy":
                bucket.buy_volume += qty
                bucket.buy_count += 1
            elif side == "sell":
                bucket.sell_volume += qty
                bucket.sell_count += 1

        return sorted(buckets.values(), key=lambda x: x.timestamp)

    except Exception as e:
        logger.warning(f"Failed to fetch trades flow for {symbol}: {e}")
        return []


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def add_flow_features(bars: list[Any], flow_data: list[TradesFlow]) -> list[Any]:
    """Add trades flow features to FeatureBar list.

    Features added:
    - buy_volume: float (total buy volume in bucket)
    - sell_volume: float (total sell volume in bucket)
    - buy_ratio: float (buy / total volume, 0.5 = neutral)
    - volume_delta: float (buy - sell volume)
    """
    if not bars:
        return bars

    # Set defaults for all bars
    for bar in bars:
        setattr(bar, "buy_volume", 0.0)
        setattr(bar, "sell_volume", 0.0)
        setattr(bar, "buy_ratio", 0.5)
        setattr(bar, "volume_delta", 0.0)

    if not flow_data:
        return bars

    # Sort flow data by timestamp
    sorted_flow = sorted(flow_data, key=lambda f: f.timestamp)

    # Match flow to bars by nearest timestamp
    flow_idx = 0

    for bar in bars:
        bar_ts = getattr(bar, "ts", 0)

        # Find closest flow bucket
        while flow_idx < len(sorted_flow) - 1 and sorted_flow[flow_idx + 1].timestamp <= bar_ts:
            flow_idx += 1

        flow = sorted_flow[flow_idx] if flow_idx < len(sorted_flow) else None
        if flow is not None:
            total_volume = flow.buy_volume + flow.sell_volume
            buy_ratio = flow.buy_volume / total_volume if total_volume > 0 else 0.5
            volume_delta = flow.buy_volume - flow.sell_volume
        else:
            buy_ratio = 0.5
            volume_delta = 0.0

        # Set attributes
        setattr(bar, "buy_volume", flow.buy_volume if flow is not None else 0.0)
        setattr(bar, "sell_volume", flow.sell_volume if flow is not None else 0.0)
        setattr(bar, "buy_ratio", buy_ratio)
        setattr(bar, "volume_delta", volume_delta)

    return bars


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def save_flow_cache(flow_data: list[TradesFlow], path: Path) -> None:
    """Save trades flow to JSON cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "symbol": f.symbol,
            "buy_volume": f.buy_volume,
            "sell_volume": f.sell_volume,
            "buy_count": f.buy_count,
            "sell_count": f.sell_count,
            "timestamp": f.timestamp,
        }
        for f in flow_data
    ]
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_flow_cache(path: Path) -> list[TradesFlow]:
    """Load trades flow from JSON cache."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [TradesFlow(**item) for item in data]
    except Exception as e:
        logger.warning(f"Failed to load flow cache: {e}")
        return []
