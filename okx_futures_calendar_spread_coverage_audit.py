"""Coverage audit for OKX futures calendar-spread research data."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from okx_futures_calendar_spread_pipeline import (
    DeliveryContract,
    parse_okx_delivery_contract,
    selected_current_contract_id,
)


ONE_MINUTE_MS = 60 * 1000


@dataclass(frozen=True)
class CloseSeries:
    instrument: str
    close_by_ts: dict[int, float]


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _day_ms(value: date, end: bool = False) -> int:
    clock = (23, 59, 59) if end else (0, 0, 0)
    return int(datetime(value.year, value.month, value.day, *clock, tzinfo=timezone.utc).timestamp() * 1000)


def _day_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()


def read_close_series(path: Path, default_instrument: str | None = None) -> CloseSeries:
    close_by_ts: dict[int, float] = {}
    instrument = default_instrument or path.name.removesuffix("_future_1m.csv").removesuffix("_swap_1m.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                timestamp_ms = int(row["timestamp_ms"])
                close = float(row["close"])
            except (KeyError, TypeError, ValueError):
                continue
            close_by_ts[timestamp_ms] = close
            if row.get("instrument_name"):
                instrument = row["instrument_name"]
    return CloseSeries(instrument=instrument, close_by_ts=close_by_ts)


def discover_futures_paths(family: str, futures_dir: Path) -> list[Path]:
    return sorted(futures_dir.glob(f"{family}-*_future_1m.csv"))


def contracts_from_futures_series(series: list[CloseSeries]) -> list[DeliveryContract]:
    contracts: list[DeliveryContract] = []
    for item in series:
        if not item.close_by_ts:
            continue
        contracts.append(parse_okx_delivery_contract(item.instrument, listed_ts=min(item.close_by_ts)))
    return sorted(contracts, key=lambda contract: contract.expiry_ts)


def audit_calendar_spread_coverage(
    family: str,
    futures_series: list[CloseSeries],
    swap_series: CloseSeries,
    start: date,
    end: date,
    min_active_days: int = 365,
) -> dict[str, Any]:
    start_ms, end_ms = _day_ms(start), _day_ms(end, True)
    contracts = contracts_from_futures_series(futures_series)
    futures_close = {item.instrument: item.close_by_ts for item in futures_series}
    aligned_timestamps: list[int] = []
    missing_selected_futures = 0
    no_selectable_contract = 0
    rows_by_contract: dict[str, int] = {}

    for ts in sorted(swap_series.close_by_ts):
        if not start_ms <= ts <= end_ms:
            continue
        selected = selected_current_contract_id(contracts, ts, family)
        if selected is None:
            no_selectable_contract += 1
            continue
        if ts not in futures_close.get(selected, {}):
            missing_selected_futures += 1
            continue
        aligned_timestamps.append(ts)
        rows_by_contract[selected] = rows_by_contract.get(selected, 0) + 1

    active_days = sorted({_day_from_ms(ts) for ts in aligned_timestamps})
    gaps = [
        {"from_ts": before, "to_ts": after, "gap_minutes": (after - before) // ONE_MINUTE_MS}
        for before, after in zip(aligned_timestamps, aligned_timestamps[1:])
        if after - before > ONE_MINUTE_MS
    ]
    passed = len(active_days) >= min_active_days and bool(rows_by_contract)
    return {
        "family": family,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "min_active_days": min_active_days,
        "passed": passed,
        "active_days": len(active_days),
        "aligned_rows": len(aligned_timestamps),
        "no_selectable_contract_rows": no_selectable_contract,
        "missing_selected_futures_rows": missing_selected_futures,
        "gap_count": len(gaps),
        "largest_gap_minutes": max((gap["gap_minutes"] for gap in gaps), default=0),
        "contracts": [{"instrument": contract.inst_id, "listed_ts": contract.listed_ts, "expiry_ts": contract.expiry_ts} for contract in contracts],
        "rows_by_contract": rows_by_contract,
        "sample_gaps": gaps[:20],
        "decision": "coverage_ready" if passed else "coverage_blocked",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit OKX futures/swap coverage for calendar-spread research.")
    parser.add_argument("--family", required=True, help="e.g. BTC-USDT")
    parser.add_argument("--futures", nargs="+", type=Path, default=[])
    parser.add_argument("--futures-dir", type=Path, default=None)
    parser.add_argument("--swap", type=Path, required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--min-active-days", type=int, default=365)
    parser.add_argument("--out", type=Path, default=Path("reports/okx_futures_calendar_spread_coverage_audit.json"))
    args = parser.parse_args(argv)
    futures_paths = list(args.futures)
    if args.futures_dir is not None:
        futures_paths.extend(discover_futures_paths(args.family, args.futures_dir))
    if not futures_paths:
        raise SystemExit("No futures files supplied. Use --futures or --futures-dir.")
    futures_series = [read_close_series(path) for path in futures_paths]
    swap_series = read_close_series(args.swap, default_instrument=f"{args.family}-SWAP")
    report = audit_calendar_spread_coverage(
        args.family,
        futures_series,
        swap_series,
        _parse_day(args.start),
        _parse_day(args.end),
        args.min_active_days,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
