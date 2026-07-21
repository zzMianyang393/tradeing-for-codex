"""Download and aggregate Binance COIN-M daily liquidation snapshots."""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


BASE_URL = "https://data.binance.vision/data/futures/cm/daily/liquidationSnapshot"


def archive_url(symbol: str, day: date) -> str:
    value = day.isoformat()
    return f"{BASE_URL}/{symbol}/{symbol}-liquidationSnapshot-{value}.zip"


def fetch_day(symbol: str, day: date) -> dict[str, float | int] | None:
    request = urllib.request.Request(archive_url(symbol, day), headers={"User-Agent": "tradering-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = next(name for name in archive.namelist() if name.endswith(".csv"))
        with archive.open(name) as handle:
            rows = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig"))
            summary: dict[str, float | int] = {"buy_count": 0, "sell_count": 0, "buy_contracts": 0.0, "sell_contracts": 0.0}
            for row in rows:
                side = row.get("side", "").upper()
                try:
                    quantity = float(row.get("original_quantity") or 0.0)
                except ValueError:
                    quantity = 0.0
                if side == "BUY":
                    summary["buy_count"] = int(summary["buy_count"]) + 1
                    summary["buy_contracts"] = float(summary["buy_contracts"]) + quantity
                elif side == "SELL":
                    summary["sell_count"] = int(summary["sell_count"]) + 1
                    summary["sell_contracts"] = float(summary["sell_contracts"]) + quantity
    summary["total_count"] = int(summary["buy_count"]) + int(summary["sell_count"])
    summary["total_contracts"] = float(summary["buy_contracts"]) + float(summary["sell_contracts"])
    return summary


def download_liquidations(symbol: str, start: date, end: date, out_dir: Path, workers: int = 1) -> dict[str, Any]:
    path = out_dir / f"{symbol}_binance_cm_liquidations.csv"
    existing: dict[str, dict[str, str]] = {}
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            existing = {row["archive_date"]: row for row in csv.DictReader(handle)}
    dates = []
    current = start
    while current <= end:
        if current.isoformat() not in existing:
            dates.append(current)
        current += timedelta(days=1)
    missing = downloaded = 0
    if workers <= 1:
        responses = ((day, fetch_day(symbol, day)) for day in dates)
        for day, summary in responses:
            if summary is None:
                missing += 1
            else:
                existing[day.isoformat()] = {"archive_date": day.isoformat(), "source": "binance_coin_m_liquidation_snapshot", **{key: str(value) for key, value in summary.items()}}
                downloaded += 1
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_day, symbol, day): day for day in dates}
            for future in as_completed(futures):
                day = futures[future]
                summary = future.result()
                if summary is None:
                    missing += 1
                else:
                    existing[day.isoformat()] = {"archive_date": day.isoformat(), "source": "binance_coin_m_liquidation_snapshot", **{key: str(value) for key, value in summary.items()}}
                    downloaded += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = ["archive_date", "source", "buy_count", "sell_count", "total_count", "buy_contracts", "sell_contracts", "total_contracts"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(existing[key] for key in sorted(existing))
    metadata = {"source": "binance_coin_m_daily_liquidation_snapshot", "execution_compatibility": "research_native_only_not_okx_execution", "symbol": symbol, "rows": len(existing), "downloaded_this_run": downloaded, "missing_archives_this_run": missing, "start": start.isoformat(), "end": end.isoformat()}
    metadata["expected_days"] = (end - start).days + 1
    metadata["coverage_ratio"] = round(len(existing) / metadata["expected_days"], 4) if metadata["expected_days"] else 0.0
    path.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Binance COIN-M daily liquidation snapshots.")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD_PERP", "ETHUSD_PERP"])
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", type=Path, default=Path("data/external"))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--min-coverage", type=float, default=0.90)
    args = parser.parse_args(argv)
    passed = True
    for symbol in args.symbols:
        metadata = download_liquidations(symbol, _parse_day(args.start), _parse_day(args.end), args.out, max(1, args.workers))
        print(json.dumps(metadata), flush=True)
        passed = passed and float(metadata["coverage_ratio"]) >= args.min_coverage
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
