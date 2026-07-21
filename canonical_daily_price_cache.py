"""Incrementally materialize compact daily OHLCV maps for account replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from canonical_strategy_account_replay import CACHE, load, load_daily_price_maps


def write_batch(bases: list[str], data_dir: Path = Path("data"), cache_path: Path = CACHE) -> int:
    existing = load(cache_path) or {}
    events = [{"symbol": f"{base}-USDT-SWAP"} for base in bases]
    maps = load_daily_price_maps(data_dir, events)
    for symbol, bars in maps.items():
        existing[symbol] = [
            {"ts": bar.ts, "timestamp_utc": bar.timestamp_utc, "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close, "volume": bar.volume}
            for _ts, bar in sorted(bars.items())
        ]
    cache_path.write_text(json.dumps(existing, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"cached={','.join(sorted(bases))}; symbols={len(existing)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bases", nargs="+")
    args = parser.parse_args()
    return write_batch(args.bases)


if __name__ == "__main__":
    raise SystemExit(main())
