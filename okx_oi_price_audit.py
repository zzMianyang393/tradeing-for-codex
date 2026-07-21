"""Time-ordered descriptive audit of daily OKX OI and subsequent price moves."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any


MATERIAL_OI_CHANGE = 0.05


def load_daily_price(path: Path) -> dict[str, tuple[float, float]]:
    """Aggregate 15m OHLCV into UTC daily open/close without using later days."""
    daily: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                day = datetime.fromisoformat(row["timestamp"]).date().isoformat()
                opening, closing = float(row["open"]), float(row["close"])
            except (KeyError, ValueError):
                continue
            if day not in daily:
                daily[day] = [opening, closing]
            else:
                daily[day][1] = closing
    return {day: (values[0], values[1]) for day, values in daily.items()}


def load_daily_oi(path: Path) -> dict[str, float]:
    values: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                day = row["timestamp_utc"].split(" ", 1)[0]
                values[day] = float(row["open_interest_usd"])
            except (KeyError, ValueError):
                continue
    return values


def _summary(returns: list[float]) -> dict[str, float | int]:
    return {
        "events": len(returns),
        "mean_return_pct": mean(returns) * 100.0 if returns else 0.0,
        "median_return_pct": median(returns) * 100.0 if returns else 0.0,
        "positive_rate": sum(value > 0 for value in returns) / len(returns) if returns else 0.0,
    }


def audit_symbol(price_by_day: dict[str, tuple[float, float]], oi_by_day: dict[str, float]) -> dict[str, Any]:
    days = sorted(set(price_by_day) & set(oi_by_day))
    buckets_1d: dict[str, list[float]] = defaultdict(list)
    buckets_3d: dict[str, list[float]] = defaultdict(list)
    for index in range(1, len(days) - 3):
        day, previous_day = days[index], days[index - 1]
        entry_day = days[index + 1]
        if oi_by_day[previous_day] <= 0 or price_by_day[previous_day][1] <= 0 or price_by_day[entry_day][0] <= 0:
            continue
        oi_change = oi_by_day[day] / oi_by_day[previous_day] - 1.0
        completed_price_change = price_by_day[day][1] / price_by_day[previous_day][1] - 1.0
        if abs(oi_change) < MATERIAL_OI_CHANGE:
            continue
        oi_direction = "oi_up" if oi_change > 0 else "oi_down"
        price_direction = "price_up" if completed_price_change > 0 else "price_down"
        bucket = f"{oi_direction}_{price_direction}"
        # Daily OI can be a completed-day snapshot.  Enter only after that
        # day's close, at the following day's open.
        forward_1d = price_by_day[entry_day][1] / price_by_day[entry_day][0] - 1.0
        third_day = days[index + 3]
        forward_3d = price_by_day[third_day][1] / price_by_day[entry_day][0] - 1.0
        buckets_1d[bucket].append(forward_1d)
        buckets_3d[bucket].append(forward_3d)
    return {
        "aligned_days": len(days),
        "event_definition": "abs(daily_oi_usd_change)>=5%; OI and price use completed signal day; returns begin at following day open",
        "one_day": {key: _summary(buckets_1d[key]) for key in sorted(buckets_1d)},
        "three_day": {key: _summary(buckets_3d[key]) for key in sorted(buckets_3d)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit OI/price event outcomes without generating trade signals.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--out", type=Path, default=Path("reports/okx_oi_price_audit.json"))
    args = parser.parse_args(argv)
    report = {
        symbol: audit_symbol(
            load_daily_price(args.data / f"{symbol}_15m.csv"),
            load_daily_oi(args.data / f"{symbol}-USDT-SWAP_open_interest_1d.csv"),
        )
        for symbol in args.symbols
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
