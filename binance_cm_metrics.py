"""Resumable downloader for Binance COIN-M daily futures metrics archives.

This source is a long-history market-structure proxy, not an OKX execution
dataset. Raw CSV columns are retained to make schema changes visible.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BASE_URL = "https://data.binance.vision/data/futures/cm/daily/metrics"


def archive_url(symbol: str, day: date) -> str:
    day_text = day.isoformat()
    return f"{BASE_URL}/{symbol}/{symbol}-metrics-{day_text}.zip"


def fetch_day(symbol: str, day: date) -> dict[str, str] | None:
    try:
        with urllib.request.urlopen(archive_url(symbol, day), timeout=30) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if not names:
            return None
        with archive.open(names[0]) as handle:
            rows = list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")))
    if not rows:
        return None
    return {str(key): str(value) for key, value in rows[0].items()}


def _load_existing_dates(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row.get("archive_date", "") for row in csv.DictReader(handle)}


def field_coverage(records: list[dict[str, str]], fieldnames: list[str]) -> dict[str, dict[str, float | int]]:
    """Return non-empty coverage for every raw archive field.

    Binance can add a column partway through the archive history.  A combined
    CSV then has a valid schema but not necessarily enough observations for a
    long-window strategy, so row count alone is not an adequate quality check.
    """
    total = len(records)
    return {
        field: {
            "non_empty_rows": sum(1 for row in records if row.get(field, "").strip()),
            "coverage_ratio": (sum(1 for row in records if row.get(field, "").strip()) / total) if total else 0.0,
        }
        for field in fieldnames
    }


def download_metrics(
    symbol: str,
    start: date,
    end: date,
    out_dir: Path,
    sleep_seconds: float = 0.1,
    workers: int = 1,
) -> dict[str, Any]:
    path = out_dir / f"{symbol}_binance_cm_metrics.csv"
    existing_dates = _load_existing_dates(path)
    records: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            records.extend(csv.DictReader(handle))
    days: list[date] = []
    current = start
    while current <= end:
        if current.isoformat() not in existing_dates:
            days.append(current)
        current += timedelta(days=1)

    attempted = downloaded = missing = 0
    attempted = len(days)
    if workers <= 1:
        fetched = ((day, fetch_day(symbol, day)) for day in days)
        for day, row in fetched:
            if row is None:
                missing += 1
            else:
                records.append({"source": "binance_coin_m_archive", "archive_date": day.isoformat(), **row})
                downloaded += 1
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_day, symbol, day): day for day in days}
            for future in as_completed(futures):
                day = futures[future]
                row = future.result()
                if row is None:
                    missing += 1
                else:
                    records.append({"source": "binance_coin_m_archive", "archive_date": day.isoformat(), **row})
                    downloaded += 1

    fieldnames = sorted({key for row in records for key in row})
    records.sort(key=lambda row: row.get("archive_date", ""))
    out_dir.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    metadata = {
        "source": "binance_coin_m_daily_metrics_archive",
        "execution_compatibility": "research_proxy_only_not_okx_execution",
        "symbol": symbol,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "rows": len(records),
        "downloaded_this_run": downloaded,
        "missing_archives_this_run": missing,
        "fieldnames": fieldnames,
        "field_coverage": field_coverage(records, fieldnames),
    }
    path.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Binance COIN-M daily metrics as research proxy data.")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD_PERP", "ETHUSD_PERP"])
    parser.add_argument("--start", required=True, help="UTC YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="UTC YYYY-MM-DD, defaults to yesterday")
    parser.add_argument("--out", type=Path, default=Path("data/external"))
    parser.add_argument("--sleep", type=float, default=0.1)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    start = _parse_day(args.start)
    end = _parse_day(args.end) if args.end else datetime.now(timezone.utc).date() - timedelta(days=1)
    if start > end:
        parser.error("--start must not be after --end")
    for symbol in args.symbols:
        metadata = download_metrics(symbol, start, end, args.out, args.sleep, max(1, args.workers))
        print(json.dumps(metadata, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
