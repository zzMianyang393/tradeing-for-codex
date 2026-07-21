"""Build spread-first OKX futures calendar-spread series from audited data."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from okx_futures_calendar_spread_coverage_audit import discover_futures_paths, read_close_series
from okx_futures_calendar_spread_pipeline import build_spread_rows, format_utc, parse_okx_delivery_contract


def _parse_day(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def write_spread_series(family: str, futures_dir: Path, swap_path: Path, out_path: Path) -> dict[str, Any]:
    futures_series = [read_close_series(path) for path in discover_futures_paths(family, futures_dir)]
    if not futures_series:
        raise RuntimeError(f"No futures files found for {family} in {futures_dir}")
    swap_series = read_close_series(swap_path, default_instrument=f"{family}-SWAP")
    contracts = [parse_okx_delivery_contract(series.instrument, listed_ts=min(series.close_by_ts)) for series in futures_series if series.close_by_ts]
    futures_close_by_inst = {series.instrument: series.close_by_ts for series in futures_series}
    rows = build_spread_rows(futures_close_by_inst, swap_series.close_by_ts, contracts, family)
    if not rows:
        raise RuntimeError(f"No aligned spread rows generated for {family}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["timestamp_ms", "timestamp_utc", "future_inst_id", "future_close", "swap_close", "spread_abs", "spread_pct"]
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "timestamp_ms": row.ts,
                "timestamp_utc": format_utc(row.ts),
                "future_inst_id": row.future_inst_id,
                "future_close": f"{row.future_close:.10f}",
                "swap_close": f"{row.swap_close:.10f}",
                "spread_abs": f"{row.spread_abs:.10f}",
                "spread_pct": f"{row.spread_pct:.12f}",
            })

    metadata = {
        "source": "okx_historical_market_data_archive",
        "execution_compatibility": "okx_execution_compatible",
        "family": family,
        "frequency": "1m",
        "rows": len(rows),
        "first_timestamp_utc": format_utc(rows[0].ts),
        "last_timestamp_utc": format_utc(rows[-1].ts),
        "future_contracts": sorted({row.future_inst_id for row in rows}),
        "construction": "spread_first_no_futures_price_stitching",
        "rollover_rule": "select_delivery_contract_until_72h_before_expiry",
    }
    out_path.with_suffix(".meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build OKX futures-vs-swap spread-first 1m series.")
    parser.add_argument("--family", required=True)
    parser.add_argument("--futures-dir", type=Path, required=True)
    parser.add_argument("--swap", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(write_spread_series(args.family, args.futures_dir, args.swap, args.out), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
