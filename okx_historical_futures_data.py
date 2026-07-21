"""Stream official OKX delivery futures candle archives for calendar-spread research."""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


HISTORY_URL = "https://openapi.okx.com/api/v5/public/market-data-history"
CANDLE_MODULE = 2
FUTURES_INST_TYPE = "FUTURES"


@dataclass(frozen=True)
class FuturesCandle:
    instrument_name: str
    timestamp_ms: int
    timestamp_utc: str
    open: str
    high: str
    low: str
    close: str
    volume_quote: str


def _day_ms(value: date, end: bool = False) -> int:
    clock = (23, 59, 59) if end else (0, 0, 0)
    return int(datetime(value.year, value.month, value.day, *clock, tzinfo=timezone.utc).timestamp() * 1000)


def _format_utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _manifest_page(family: str, start: date, end: date) -> list[dict[str, str]]:
    params = {
        "module": str(CANDLE_MODULE),
        "instType": FUTURES_INST_TYPE,
        "dateAggrType": "monthly",
        "instFamilyList": family,
        "begin": str(_day_ms(start)),
        "end": str(_day_ms(end, True)),
    }
    request = urllib.request.Request(f"{HISTORY_URL}?{urllib.parse.urlencode(params)}", headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX futures candle manifest failed for {family}: {payload}")
    return [entry for group in payload.get("data", []) for detail in group.get("details", []) for entry in detail.get("groupDetails", [])]


def list_futures_archives(family: str, start: date, end: date) -> list[dict[str, str]]:
    """List official OKX monthly FUTURES candle archives for an instrument family."""
    archives: dict[str, dict[str, str]] = {}
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=61), end)
        for entry in _manifest_page(family, cursor, window_end):
            if entry.get("url"):
                archives[entry["url"]] = entry
        cursor = window_end + timedelta(days=1)
    return sorted(archives.values(), key=lambda entry: entry.get("dateTs", ""))


def futures_output_path(instrument_name: str, out_dir: Path) -> Path:
    return out_dir / f"{instrument_name}_future_1m.csv"


def _row_to_candle(row: dict[str, str], start_ms: int, end_ms: int, allowed: set[str] | None) -> FuturesCandle | None:
    try:
        timestamp_ms = int(row["open_time"])
    except (KeyError, TypeError, ValueError):
        return None
    instrument_name = row.get("instrument_name", "")
    if not start_ms <= timestamp_ms <= end_ms:
        return None
    if row.get("confirm") != "1":
        return None
    if allowed is not None and instrument_name not in allowed:
        return None
    return FuturesCandle(
        instrument_name=instrument_name,
        timestamp_ms=timestamp_ms,
        timestamp_utc=_format_utc(timestamp_ms),
        open=row.get("open", ""),
        high=row.get("high", ""),
        low=row.get("low", ""),
        close=row.get("close", ""),
        volume_quote=row.get("vol_quote", ""),
    )


def _stream_archive_rows(url: str, start_ms: int, end_ms: int, allowed: set[str] | None) -> list[FuturesCandle]:
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read()
    rows: list[FuturesCandle] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.endswith(".csv")]
        if not names:
            raise RuntimeError("OKX futures candle archive does not contain csv files")
        for name in names:
            with archive.open(name) as handle:
                for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
                    candle = _row_to_candle(row, start_ms, end_ms, allowed)
                    if candle is not None:
                        rows.append(candle)
    return rows


def download_futures_archive(url: str, start: date, end: date, contract_ids: Iterable[str] | None = None) -> list[FuturesCandle]:
    allowed = set(contract_ids) if contract_ids is not None else None
    return _stream_archive_rows(url, _day_ms(start), _day_ms(end, True), allowed)


def _write_contract_file(path: Path, rows: list[FuturesCandle]) -> None:
    headers = ["timestamp_ms", "timestamp_utc", "instrument_name", "open", "high", "low", "close", "volume_quote"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "timestamp_ms": row.timestamp_ms,
                "timestamp_utc": row.timestamp_utc,
                "instrument_name": row.instrument_name,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume_quote": row.volume_quote,
            })


def download_futures_family(
    family: str,
    start: date,
    end: date,
    out_dir: Path,
    contract_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    archives = list_futures_archives(family, start, end)
    if not archives:
        raise RuntimeError(f"No OKX futures candle archives returned for {family}")
    allowed = set(contract_ids) if contract_ids is not None else None
    rows_by_contract: dict[str, dict[int, FuturesCandle]] = defaultdict(dict)
    for archive in archives:
        for row in download_futures_archive(archive["url"], start, end, allowed):
            rows_by_contract[row.instrument_name][row.timestamp_ms] = row
    if not rows_by_contract:
        raise RuntimeError(f"No complete futures candle rows in requested range for {family}")

    out_dir.mkdir(parents=True, exist_ok=True)
    contracts: list[dict[str, Any]] = []
    for instrument_name in sorted(rows_by_contract):
        rows = [rows_by_contract[instrument_name][ts] for ts in sorted(rows_by_contract[instrument_name])]
        path = futures_output_path(instrument_name, out_dir)
        _write_contract_file(path, rows)
        metadata = {
            "source": "okx_historical_market_data_archive",
            "execution_compatibility": "okx_execution_compatible",
            "instrument": instrument_name,
            "inst_type": FUTURES_INST_TYPE,
            "family": family,
            "frequency": "1m",
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "rows": len(rows),
            "archives": len(archives),
            "archive_filenames": [entry.get("filename", "") for entry in archives],
            "contract_filter": sorted(allowed) if allowed is not None else [],
        }
        path.with_suffix(".meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        contracts.append({"instrument": instrument_name, "rows": len(rows), "path": str(path)})

    manifest = {
        "source": "okx_historical_market_data_archive",
        "execution_compatibility": "okx_execution_compatible",
        "family": family,
        "inst_type": FUTURES_INST_TYPE,
        "frequency": "1m",
        "requested_start": start.isoformat(),
        "requested_end": end.isoformat(),
        "archives": len(archives),
        "archive_filenames": [entry.get("filename", "") for entry in archives],
        "contracts": contracts,
    }
    manifest_path = out_dir / f"{family}_futures_1m_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download OKX delivery futures 1m candles for calendar-spread research.")
    parser.add_argument("--families", nargs="+", required=True, help="e.g. BTC-USDT ETH-USDT")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--out", type=Path, default=Path("data/calendar_spread"))
    parser.add_argument("--contract-ids", nargs="*", default=None, help="Optional delivery contract ids, e.g. BTC-USDT-240927")
    args = parser.parse_args(argv)
    start, end = _parse_day(args.start), _parse_day(args.end)
    for family in args.families:
        print(json.dumps(download_futures_family(family, start, end, args.out, args.contract_ids), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
