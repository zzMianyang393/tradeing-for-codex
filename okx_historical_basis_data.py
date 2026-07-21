"""Stream official OKX spot and perpetual candle archives for basis research."""

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


HISTORY_URL = "https://openapi.okx.com/api/v5/public/market-data-history"
CANDLE_MODULE = 2


def _day_ms(value: date, end: bool = False) -> int:
    clock = (23, 59, 59) if end else (0, 0, 0)
    return int(datetime(value.year, value.month, value.day, *clock, tzinfo=timezone.utc).timestamp() * 1000)


def _format_utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _manifest_page(instrument: str, inst_type: str, start: date, end: date) -> list[dict[str, str]]:
    params = {"module": str(CANDLE_MODULE), "instType": inst_type, "dateAggrType": "monthly", "begin": str(_day_ms(start)), "end": str(_day_ms(end, True))}
    if inst_type == "SPOT":
        params["instIdList"] = instrument
    else:
        params["instFamilyList"] = instrument.removesuffix("-SWAP")
    request = urllib.request.Request(f"{HISTORY_URL}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX candle manifest failed for {instrument}: {payload}")
    return [entry for group in payload.get("data", []) for detail in group.get("details", []) for entry in detail.get("groupDetails", [])]


def list_candle_archives(instrument: str, inst_type: str, start: date, end: date) -> list[dict[str, str]]:
    archives: dict[str, dict[str, str]] = {}
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=61), end)
        for entry in _manifest_page(instrument, inst_type, cursor, window_end):
            if entry.get("url"):
                archives[entry["url"]] = entry
        cursor = window_end + timedelta(days=1)
    return sorted(archives.values(), key=lambda entry: entry.get("dateTs", ""))


def output_path(pair: str, inst_type: str, out_dir: Path) -> Path:
    leg = "spot" if inst_type == "SPOT" else "swap"
    return out_dir / f"{pair}_{leg}_1m.csv"


def _stream_archive(url: str, expected_instrument: str, writer: csv.DictWriter, start_ms: int, end_ms: int) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read()
    written = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"Unexpected OKX candle archive entries: {names}")
        with archive.open(names[0]) as handle:
            for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
                try:
                    timestamp_ms = int(row["open_time"])
                    if not start_ms <= timestamp_ms <= end_ms or row["instrument_name"] != expected_instrument or row.get("confirm") != "1":
                        continue
                    writer.writerow({
                        "timestamp_ms": timestamp_ms, "timestamp_utc": _format_utc(timestamp_ms),
                        "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"],
                        "volume_quote": row.get("vol_quote", ""),
                    })
                    written += 1
                except (KeyError, TypeError, ValueError):
                    continue
    return written


def download_leg(pair: str, inst_type: str, start: date, end: date, out_dir: Path) -> dict[str, Any]:
    instrument = pair if inst_type == "SPOT" else f"{pair}-SWAP"
    archives = list_candle_archives(instrument, inst_type, start, end)
    if not archives:
        raise RuntimeError(f"No OKX candle archives returned for {instrument}")
    path = output_path(pair, inst_type, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["timestamp_ms", "timestamp_utc", "open", "high", "low", "close", "volume_quote"]
    rows = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for archive in archives:
            rows += _stream_archive(archive["url"], instrument, writer, _day_ms(start), _day_ms(end, True))
    if rows == 0:
        raise RuntimeError(f"No complete candle rows in requested range for {instrument}")
    metadata = {
        "source": "okx_historical_market_data_archive",
        "execution_compatibility": "okx_execution_compatible",
        "instrument": instrument,
        "inst_type": inst_type,
        "frequency": "1m",
        "requested_start": start.isoformat(), "requested_end": end.isoformat(),
        "rows": rows, "archives": len(archives), "archive_filenames": [entry.get("filename", "") for entry in archives],
    }
    path.with_suffix(".meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download OKX spot/swap 1m candles for basis research.")
    parser.add_argument("--pairs", nargs="+", required=True, help="e.g. BTC-USDT ETH-USDT")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--out", type=Path, default=Path("data/basis"))
    args = parser.parse_args(argv)
    start, end = _parse_day(args.start), _parse_day(args.end)
    for pair in args.pairs:
        for inst_type in ("SPOT", "SWAP"):
            print(json.dumps(download_leg(pair, inst_type, start, end, args.out), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
