"""Descriptive audit for OKX futures calendar-spread series."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from okx_futures_calendar_spread_pipeline import FOUR_LEG_ROUND_TRIP_COST


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    index = (len(sorted_values) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _day_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()


def descriptive_audit(spread_path: Path, cost_floor: float = FOUR_LEG_ROUND_TRIP_COST) -> dict[str, Any]:
    values: list[float] = []
    abs_values: list[float] = []
    days: set[str] = set()
    rows_by_contract: dict[str, int] = {}
    above_cost = 0
    first_ts: int | None = None
    last_ts: int | None = None

    with spread_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                timestamp_ms = int(row["timestamp_ms"])
                spread_pct = float(row["spread_pct"])
            except (KeyError, TypeError, ValueError):
                continue
            first_ts = timestamp_ms if first_ts is None else min(first_ts, timestamp_ms)
            last_ts = timestamp_ms if last_ts is None else max(last_ts, timestamp_ms)
            values.append(spread_pct)
            abs_value = abs(spread_pct)
            abs_values.append(abs_value)
            above_cost += int(abs_value >= cost_floor)
            days.add(_day_from_ms(timestamp_ms))
            contract = row.get("future_inst_id", "")
            rows_by_contract[contract] = rows_by_contract.get(contract, 0) + 1

    values.sort()
    abs_values.sort()
    rows = len(values)
    if rows == 0:
        raise RuntimeError(f"No spread rows found in {spread_path}")
    return {
        "spread_path": str(spread_path),
        "rows": rows,
        "active_days": len(days),
        "first_timestamp_ms": first_ts,
        "last_timestamp_ms": last_ts,
        "cost_floor": cost_floor,
        "abs_spread_ge_cost_rows": above_cost,
        "abs_spread_ge_cost_ratio": above_cost / rows,
        "spread_pct_mean": sum(values) / rows,
        "spread_pct_min": values[0],
        "spread_pct_max": values[-1],
        "spread_pct_p05": _quantile(values, 0.05),
        "spread_pct_p50": _quantile(values, 0.50),
        "spread_pct_p95": _quantile(values, 0.95),
        "abs_spread_pct_p50": _quantile(abs_values, 0.50),
        "abs_spread_pct_p75": _quantile(abs_values, 0.75),
        "abs_spread_pct_p95": _quantile(abs_values, 0.95),
        "abs_spread_pct_p99": _quantile(abs_values, 0.99),
        "contracts": sorted(rows_by_contract),
        "rows_by_contract": rows_by_contract,
        "decision": "descriptive_only_not_strategy",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Describe OKX futures calendar spread amplitude.")
    parser.add_argument("--spread", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/okx_futures_calendar_spread_descriptive_audit.json"))
    parser.add_argument("--cost-floor", type=float, default=FOUR_LEG_ROUND_TRIP_COST)
    args = parser.parse_args(argv)
    report = descriptive_audit(args.spread, args.cost_floor)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
