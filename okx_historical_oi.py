"""Resumable daily open-interest downloader from the official OKX history API."""

from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


HISTORY_URL = "https://openapi.okx.com/api/v5/rubik/stat/contracts/open-interest-history"
DAY_MS = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class DailyOpenInterest:
    symbol: str
    ts: int
    timestamp_utc: str
    open_interest: float
    open_interest_currency: float
    open_interest_usd: float


def _day_start_ms(value: date) -> int:
    return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp() * 1000)


def _format_utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def fetch_oi_page(symbol: str, end: int | None = None, limit: int = 100) -> list[list[str]]:
    params = {"instId": symbol, "period": "1D", "limit": str(limit)}
    if end is not None:
        params["end"] = str(end)
    request = urllib.request.Request(
        f"{HISTORY_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "tradering-research/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX OI history failed for {symbol}: {payload}")
    return payload.get("data", [])


def parse_oi_rows(symbol: str, rows: list[list[str]]) -> list[DailyOpenInterest]:
    records: list[DailyOpenInterest] = []
    for row in rows:
        try:
            timestamp_ms = int(row[0])
            records.append(DailyOpenInterest(
                symbol=symbol, ts=timestamp_ms, timestamp_utc=_format_utc(timestamp_ms),
                open_interest=float(row[1]), open_interest_currency=float(row[2]), open_interest_usd=float(row[3]),
            ))
        except (IndexError, TypeError, ValueError):
            continue
    return records


def output_path(symbol: str, out_dir: Path) -> Path:
    return out_dir / f"{symbol}_open_interest_1d.csv"


def save_records(path: Path, records: list[DailyOpenInterest]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(records[0]).keys()) if records else [
            "symbol", "ts", "timestamp_utc", "open_interest", "open_interest_currency", "open_interest_usd",
        ])
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)


def download_daily_oi(symbol: str, start: date, end: date, out_dir: Path, limit: int = 100) -> dict[str, Any]:
    if start > end:
        raise ValueError("start must not be after end")
    start_ms, end_ms = _day_start_ms(start), _day_start_ms(end)
    records: dict[int, DailyOpenInterest] = {}
    cursor: int | None = None
    pages = 0
    while True:
        rows = fetch_oi_page(symbol, end=cursor, limit=limit)
        pages += 1
        parsed = parse_oi_rows(symbol, rows)
        if not parsed:
            break
        for record in parsed:
            if start_ms <= record.ts <= end_ms:
                records[record.ts] = record
        oldest = min(record.ts for record in parsed)
        if oldest <= start_ms or len(rows) < limit:
            break
        next_cursor = oldest - 1
        if cursor is not None and next_cursor >= cursor:
            raise RuntimeError(f"OKX OI pagination did not move backwards for {symbol}")
        cursor = next_cursor

    ordered = [records[key] for key in sorted(records)]
    if not ordered:
        raise RuntimeError(f"No OKX OI records in requested range for {symbol}: {start}..{end}")
    path = output_path(symbol, out_dir)
    save_records(path, ordered)
    metadata = {
        "source": "okx_open_interest_history",
        "execution_compatibility": "okx_execution_compatible",
        "symbol": symbol,
        "period": "1D",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "rows": len(ordered),
        "first_ts": ordered[0].ts,
        "last_ts": ordered[-1].ts,
        "pages": pages,
    }
    path.with_suffix(".meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download paginated daily OKX open-interest history.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="UTC YYYY-MM-DD")
    parser.add_argument("--end", default=datetime.now(timezone.utc).date().isoformat(), help="UTC YYYY-MM-DD")
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    for symbol in args.symbols:
        print(json.dumps(download_daily_oi(symbol, _parse_day(args.start), _parse_day(args.end), args.out), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
