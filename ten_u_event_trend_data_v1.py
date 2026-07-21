"""Dedicated causal data pipeline for the 10U event-trend research.

The legacy hourly CSV writer stores base volume in a generic ``volume``
column.  This candidate is pre-registered on quote volume, so it requires an
isolated full-field dataset with explicit units and a reproducible manifest.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


OKX_HISTORY_URL = "https://www.okx.com/api/v5/market/history-candles"
OKX_INSTRUMENT_URL = "https://www.okx.com/api/v5/public/instruments"
HOUR_MS = 3_600_000


def parse_utc(value: str) -> int:
    if not value.endswith("Z"):
        raise ValueError("timestamps must have an explicit UTC Z suffix")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return int(parsed.timestamp() * 1000)


def format_utc(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class FullHourlyCandle:
    timestamp_ms: int
    timestamp_utc: str
    open: str
    high: str
    low: str
    close: str
    volume_contracts: str
    volume_base: str
    volume_quote: str
    confirmed: bool

    @classmethod
    def from_okx(cls, row: list[str]) -> "FullHourlyCandle":
        if len(row) < 9:
            raise ValueError(f"expected nine OKX candle fields, received {len(row)}")
        timestamp_ms = int(row[0])
        return cls(
            timestamp_ms=timestamp_ms,
            timestamp_utc=format_utc(timestamp_ms),
            open=row[1],
            high=row[2],
            low=row[3],
            close=row[4],
            volume_contracts=row[5],
            volume_base=row[6],
            volume_quote=row[7],
            confirmed=row[8] == "1",
        )


FetchPage = Callable[[str, int | None, int], list[list[str]]]


def fetch_page(symbol: str, after: int | None, limit: int = 100) -> list[list[str]]:
    params: dict[str, str | int] = {"instId": symbol, "bar": "1H", "limit": limit}
    if after is not None:
        params["after"] = after
    request = Request(
        f"{OKX_HISTORY_URL}?{urlencode(params)}",
        headers={"User-Agent": "tradering-research/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX history error for {symbol}: {payload}")
    return payload.get("data", [])


def fetch_instrument(symbol: str) -> dict[str, Any]:
    params = urlencode({"instType": "SWAP", "instId": symbol})
    request = Request(
        f"{OKX_INSTRUMENT_URL}?{params}",
        headers={"User-Agent": "tradering-research/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("code") != "0" or len(payload.get("data", [])) != 1:
        raise RuntimeError(f"OKX instrument error for {symbol}: {payload}")
    raw = payload["data"][0]
    return {
        key: raw.get(key)
        for key in (
            "instId",
            "state",
            "listTime",
            "lever",
            "ctVal",
            "ctValCcy",
            "lotSz",
            "minSz",
            "tickSz",
            "settleCcy",
        )
    }


def collect_completed_hourly(
    symbol: str,
    start_ms: int,
    end_ms: int,
    *,
    page_fetcher: FetchPage = fetch_page,
    sleep_seconds: float = 0.12,
) -> list[FullHourlyCandle]:
    if start_ms >= end_ms or start_ms % HOUR_MS or end_ms % HOUR_MS:
        raise ValueError("hourly range must be aligned and non-empty")
    rows: dict[int, FullHourlyCandle] = {}
    after: int | None = None
    previous_oldest: int | None = None
    while True:
        page = page_fetcher(symbol, after, 100)
        if not page:
            break
        candles = [FullHourlyCandle.from_okx(row) for row in page]
        for candle in candles:
            if start_ms <= candle.timestamp_ms < end_ms and candle.confirmed:
                rows[candle.timestamp_ms] = candle
        oldest = min(candle.timestamp_ms for candle in candles)
        if oldest <= start_ms:
            break
        if previous_oldest is not None and oldest >= previous_oldest:
            raise RuntimeError("OKX pagination did not move backward")
        previous_oldest = oldest
        after = oldest
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return [rows[timestamp] for timestamp in sorted(rows)]


def validate_hourly(candles: Iterable[FullHourlyCandle]) -> dict[str, Any]:
    ordered = list(candles)
    if not ordered:
        return {"status": "FAIL", "rows": 0, "missing_hours": [], "reasons": ["no_rows"]}
    timestamps = [candle.timestamp_ms for candle in ordered]
    reasons: list[str] = []
    if timestamps != sorted(set(timestamps)):
        reasons.append("timestamps_not_strictly_increasing")
    if any(not candle.confirmed for candle in ordered):
        reasons.append("contains_unconfirmed_candle")
    missing: list[int] = []
    for left, right in zip(timestamps, timestamps[1:]):
        if right - left > HOUR_MS:
            missing.extend(range(left + HOUR_MS, right, HOUR_MS))
        elif right - left != HOUR_MS:
            reasons.append("non_hourly_timestamp")
    for candle in ordered:
        open_, high, low, close = map(
            float, (candle.open, candle.high, candle.low, candle.close)
        )
        if min(open_, high, low, close) <= 0 or high < max(open_, close) or low > min(
            open_, close
        ):
            reasons.append(f"invalid_ohlc:{candle.timestamp_ms}")
            break
        if float(candle.volume_quote) < 0:
            reasons.append(f"negative_quote_volume:{candle.timestamp_ms}")
            break
    return {
        "status": "PASS" if not reasons and not missing else "FAIL",
        "rows": len(ordered),
        "first_timestamp": ordered[0].timestamp_utc,
        "last_timestamp": ordered[-1].timestamp_utc,
        "missing_hours": [format_utc(timestamp) for timestamp in missing],
        "reasons": reasons,
    }


CSV_FIELDS = tuple(FullHourlyCandle.__dataclass_fields__)


def write_hourly(path: Path, candles: list[FullHourlyCandle]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for candle in candles:
            row = asdict(candle)
            row["confirmed"] = "1" if candle.confirmed else "0"
            writer.writerow(row)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_hourly(path: Path) -> list[FullHourlyCandle]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            FullHourlyCandle(
                timestamp_ms=int(row["timestamp_ms"]),
                timestamp_utc=row["timestamp_utc"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume_contracts=row["volume_contracts"],
                volume_base=row["volume_base"],
                volume_quote=row["volume_quote"],
                confirmed=row["confirmed"] == "1",
            )
            for row in csv.DictReader(handle)
        ]


def download_dataset(
    symbols: list[str], start: str, end: str, out_dir: Path
) -> dict[str, Any]:
    start_ms, end_ms = parse_utc(start), parse_utc(end)
    manifest: dict[str, Any] = {
        "dataset_id": "ten_u_event_trend_full_hourly_v1",
        "source": "OKX public history-candles and public instruments",
        "requested_start": start,
        "requested_end": end,
        "bar": "1H",
        "completed_only": True,
        "symbols": {},
    }
    for symbol in symbols:
        candles = collect_completed_hourly(symbol, start_ms, end_ms)
        validation = validate_hourly(candles)
        path = out_dir / f"{symbol.split('-')[0]}_1h_full.csv"
        sha256 = write_hourly(path, candles)
        manifest["symbols"][symbol] = {
            "path": str(path).replace("\\", "/"),
            "sha256": sha256,
            "instrument": fetch_instrument(symbol),
            "validation": validation,
        }
    manifest["coverage_status"] = (
        "PASS"
        if all(item["validation"]["status"] == "PASS" for item in manifest["symbols"].values())
        else "FAIL"
    )
    manifest_path = out_dir / "hourly_dataset_manifest_v1.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(download_dataset(args.symbols, args.start, args.end, args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
