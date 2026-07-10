"""Download Binance COIN-M 1d klines for native market-structure research."""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path


BASE_URL = "https://data.binance.vision/data/futures/cm"
FIELDS = ("open_time", "open", "high", "low", "close", "volume", "close_time", "base_volume", "trades", "taker_volume", "taker_base_volume", "ignore")


def month_url(symbol: str, year: int, month: int) -> str:
    value = f"{year}-{month:02d}"
    return f"{BASE_URL}/monthly/klines/{symbol}/1d/{symbol}-1d-{value}.zip"


def daily_url(symbol: str, day: date) -> str:
    value = day.isoformat()
    return f"{BASE_URL}/daily/klines/{symbol}/1d/{symbol}-1d-{value}.zip"


def _read_zip(url: str) -> list[list[str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = next(name for name in archive.namelist() if name.endswith(".csv"))
        with archive.open(name) as handle:
            rows = list(csv.reader(io.TextIOWrapper(handle, encoding="utf-8-sig")))
    if rows and rows[0] and rows[0][0].lower() in {"open_time", "open time"}:
        rows = rows[1:]
    return rows


def _month_starts(start: date, end: date) -> list[date]:
    current = date(start.year, start.month, 1)
    values = []
    while current <= end:
        values.append(current)
        current = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
    return values


def download_klines(symbol: str, start: date, end: date, out_dir: Path) -> dict[str, object]:
    records: dict[int, list[str]] = {}
    for month in _month_starts(start, end):
        if month.year == end.year and month.month == end.month:
            current = max(start, month)
            while current <= end:
                for row in _read_zip(daily_url(symbol, current)):
                    records[int(row[0])] = row
                current += timedelta(days=1)
        else:
            for row in _read_zip(month_url(symbol, month.year, month.month)):
                records[int(row[0])] = row
    selected = [row for timestamp, row in sorted(records.items()) if start <= datetime.utcfromtimestamp(timestamp / 1000).date() <= end]
    path = out_dir / f"{symbol}_binance_cm_1d.csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        writer.writerows(selected)
    metadata = {"source": "binance_coin_m_archive", "execution_compatibility": "research_native_only_not_okx_execution", "symbol": symbol, "rows": len(selected), "start": start.isoformat(), "end": end.isoformat()}
    path.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Binance COIN-M native 1d klines.")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD_PERP", "ETHUSD_PERP"])
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", type=Path, default=Path("data/external"))
    args = parser.parse_args(argv)
    start, end = _parse_day(args.start), _parse_day(args.end)
    for symbol in args.symbols:
        print(json.dumps(download_klines(symbol, start, end, args.out)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
