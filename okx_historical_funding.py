"""Download long-history OKX perpetual funding archives with provenance metadata.

OKX's ordinary funding endpoint exposes only a short rolling history.  Its
historical-market-data endpoint instead returns immutable monthly archive URLs.
This downloader normalizes those archives into the existing funding cache
format, while recording source and requested coverage for `research_data_gate`.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from funding_rate import FundingRate, load_funding_rates, save_funding_rates


HISTORY_URL = "https://openapi.okx.com/api/v5/public/market-data-history"
FUNDING_MODULE = 3


def _utc_ms(day: date, end_of_day: bool = False) -> int:
    hour = 23 if end_of_day else 0
    minute = 59 if end_of_day else 0
    second = 59 if end_of_day else 0
    return int(datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=timezone.utc).timestamp() * 1000)


def _format_utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _inst_family(symbol: str) -> str:
    if not symbol.endswith("-SWAP"):
        raise ValueError(f"Expected an OKX perpetual symbol ending in -SWAP, got {symbol}")
    return symbol.removesuffix("-SWAP")


def _list_funding_archives_page(symbol: str, start: date, end: date) -> list[dict[str, str]]:
    params = {
        "module": str(FUNDING_MODULE), "instType": "SWAP", "instFamilyList": _inst_family(symbol),
        "dateAggrType": "monthly", "begin": str(_utc_ms(start)), "end": str(_utc_ms(end, end_of_day=True)),
    }
    request = urllib.request.Request(f"{HISTORY_URL}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX historical funding manifest failed for {symbol}: {payload}")
    archives: list[dict[str, str]] = []
    for group in payload.get("data", []):
        for detail in group.get("details", []):
            archives.extend(detail.get("groupDetails", []))
    return archives


def list_funding_archives(symbol: str, start: date, end: date) -> list[dict[str, str]]:
    """Request short manifest windows and de-duplicate calendar-month overlaps.

    The endpoint returns HTTP 400 for a multi-year query.  It can also include a
    whole calendar month around the requested dates, hence URL de-duplication.
    """
    archives_by_url: dict[str, dict[str, str]] = {}
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=61), end)
        for archive in _list_funding_archives_page(symbol, cursor, window_end):
            url = archive.get("url")
            if url:
                archives_by_url[url] = archive
        cursor = window_end + timedelta(days=1)
    return sorted(archives_by_url.values(), key=lambda item: item.get("dateTs", ""))


def download_funding_archive(url: str) -> list[FundingRate]:
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"Unexpected funding archive CSV entries: {names}")
        with archive.open(names[0]) as handle:
            rows = list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")))
    records: list[FundingRate] = []
    for row in rows:
        try:
            timestamp_ms = int(row["funding_time"])
            records.append(FundingRate(
                symbol=str(row["instrument_name"]), ts=timestamp_ms,
                time=_format_utc(timestamp_ms), funding_rate=float(row["funding_rate"]),
                realized_rate=float(row["funding_rate"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return records


def download_funding_history(symbol: str, start: date, end: date, out_dir: Path) -> dict[str, Any]:
    if start > end:
        raise ValueError("start must not be after end")
    archives = list_funding_archives(symbol, start, end)
    if not archives:
        raise RuntimeError(f"No OKX historical funding archives returned for {symbol} in {start}..{end}")
    path = out_dir / f"{symbol}_funding.csv"
    merged = {record.ts: record for record in load_funding_rates(path)}
    downloaded_rows = 0
    for archive in archives:
        for record in download_funding_archive(archive["url"]):
            if _utc_ms(start) <= record.ts <= _utc_ms(end, end_of_day=True):
                if record.ts not in merged:
                    downloaded_rows += 1
                merged[record.ts] = record
    ordered = [merged[key] for key in sorted(merged)]
    save_funding_rates(path, ordered)
    metadata = {
        "source": "okx_historical_market_data_archive",
        "execution_compatibility": "okx_execution_compatible",
        "symbol": symbol,
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "rows": len(ordered),
        "downloaded_rows_this_run": downloaded_rows,
        "archives": len(archives),
        "archive_filenames": [item.get("filename", "") for item in archives],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download long-history OKX perpetual funding archives.")
    parser.add_argument("--symbols", nargs="+", required=True, help="OKX symbols, e.g. BTC-USDT-SWAP")
    parser.add_argument("--start", required=True, help="UTC YYYY-MM-DD")
    parser.add_argument("--end", default=datetime.now(timezone.utc).date().isoformat(), help="UTC YYYY-MM-DD")
    parser.add_argument("--out", type=Path, default=Path("data"))
    args = parser.parse_args(argv)
    start, end = _parse_day(args.start), _parse_day(args.end)
    for symbol in args.symbols:
        print(json.dumps(download_funding_history(symbol, start, end, args.out), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
