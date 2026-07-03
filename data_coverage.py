from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from market import _normalize_timestamp


ROWS_PER_DAY = {
    "1m": 24 * 60,
    "5m": 24 * 12,
    "15m": 24 * 4,
    "1h": 24,
    "4h": 6,
    "1d": 1,
}


def parse_timestamp(value: str) -> int:
    stripped = value.strip()
    if stripped.isdigit():
        return _normalize_timestamp(int(stripped))
    parsed = datetime.strptime(stripped, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def inspect_file(path: Path) -> dict | None:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    if not rows:
        return None
    if "timestamp_ms" in rows[0]:
        first_ts = int(rows[0]["timestamp_ms"])
        last_ts = int(rows[-1]["timestamp_ms"])
    elif "timestamp" in rows[0]:
        first_ts = parse_timestamp(rows[0]["timestamp"])
        last_ts = parse_timestamp(rows[-1]["timestamp"])
    else:
        return None
    symbol = path.name
    timeframe = "unknown"
    if symbol.endswith("_1m.csv"):
        timeframe = "1m"
        symbol = symbol.removesuffix("_1m.csv")
    elif symbol.endswith("_5m.csv"):
        timeframe = "5m"
        symbol = f"{symbol.removesuffix('_5m.csv')}-USDT-SWAP"
    elif symbol.endswith("_15m.csv"):
        timeframe = "15m"
        symbol = f"{symbol.removesuffix('_15m.csv')}-USDT-SWAP"
    elif symbol.endswith("_1h.csv"):
        timeframe = "1h"
        symbol = f"{symbol.removesuffix('_1h.csv')}-USDT-SWAP"
    elif symbol.endswith("_4h.csv"):
        timeframe = "4h"
        symbol = f"{symbol.removesuffix('_4h.csv')}-USDT-SWAP"
    elif symbol.endswith("_1d.csv"):
        timeframe = "1d"
        symbol = f"{symbol.removesuffix('_1d.csv')}-USDT-SWAP"
    span_days = (last_ts - first_ts) / 86_400_000
    days = len(rows) / ROWS_PER_DAY.get(timeframe, 1)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows": len(rows),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "days": days,
        "span_days": span_days,
        "path": str(path),
    }


def fmt(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> None:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../Quantify/data")
    records = []
    for path in data_dir.glob("*.csv"):
        info = inspect_file(path)
        if info:
            records.append(info)
    symbols = sorted({record["symbol"] for record in records if record["symbol"].endswith("-USDT-SWAP")})
    print(f"data_dir={data_dir}")
    print(f"total_unique_symbols={len(symbols)}")
    print("symbols=" + ", ".join(symbols))
    print()
    for timeframe in ("1m", "5m", "15m", "1h", "4h", "1d"):
        group = [r for r in records if r["timeframe"] == timeframe]
        if not group:
            continue
        unique = sorted({r["symbol"] for r in group})
        print(f"{timeframe}: symbols={len(unique)} files={len(group)}")
        for threshold in (30, 60, 90, 180, 365):
            eligible = sorted({r["symbol"] for r in group if r["days"] + 0.01 >= threshold})
            print(f"  >= {threshold:>3}d: {len(eligible):>2} symbols")
        top = sorted(group, key=lambda r: r["days"], reverse=True)[:8]
        for item in top:
            print(
                f"    {item['symbol']:15s} {item['days']:7.1f}d "
                f"{fmt(item['first_ts'])} -> {fmt(item['last_ts'])} rows={item['rows']}"
            )
        print()


if __name__ == "__main__":
    main()
