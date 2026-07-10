"""Download auditable Binance USD-M funding history for research only.

The files produced here must never be treated as OKX execution funding.  They
are an external market-state proxy and carry their source in both the CSV and a
sidecar metadata file.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BINANCE_FUNDING_HISTORY_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
MAX_PAGE_SIZE = 1000


@dataclass(frozen=True, slots=True)
class BinanceFundingRate:
    symbol: str
    ts: int
    time: str
    funding_rate: float
    mark_price: float


def fetch_funding_page(symbol: str, start_time: int, end_time: int, limit: int = MAX_PAGE_SIZE) -> list[dict[str, Any]]:
    params = {
        "symbol": symbol,
        "startTime": str(start_time),
        "endTime": str(end_time),
        "limit": str(min(limit, MAX_PAGE_SIZE)),
    }
    request = urllib.request.Request(
        f"{BINANCE_FUNDING_HISTORY_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "tradering-research/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Binance funding response for {symbol}: {payload}")
    return payload


def parse_rows(rows: list[dict[str, Any]]) -> list[BinanceFundingRate]:
    parsed: list[BinanceFundingRate] = []
    for row in rows:
        try:
            ts = int(row["fundingTime"])
            parsed.append(BinanceFundingRate(
                symbol=str(row["symbol"]),
                ts=ts,
                time=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                funding_rate=float(row["fundingRate"]),
                mark_price=float(row.get("markPrice") or 0.0),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(parsed, key=lambda item: item.ts)


def download_history(symbol: str, start_time: int, end_time: int, sleep_seconds: float = 0.2) -> list[BinanceFundingRate]:
    rates: dict[int, BinanceFundingRate] = {}
    cursor = start_time
    while cursor <= end_time:
        page = parse_rows(fetch_funding_page(symbol, cursor, end_time))
        if not page:
            break
        for rate in page:
            rates[rate.ts] = rate
        next_cursor = page[-1].ts + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(page) >= MAX_PAGE_SIZE and sleep_seconds > 0:
            time.sleep(sleep_seconds)
        if len(page) < MAX_PAGE_SIZE:
            break
    return [rates[ts] for ts in sorted(rates)]


def output_path(symbol: str, out_dir: Path) -> Path:
    return out_dir / f"{symbol}_binance_funding.csv"


def save_history(path: Path, rates: list[BinanceFundingRate], requested_start: int, requested_end: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source", "symbol", "timestamp_ms", "timestamp_utc", "funding_rate", "mark_price"])
        for rate in rates:
            writer.writerow(["binance_usdm", rate.symbol, rate.ts, rate.time, rate.funding_rate, rate.mark_price])
    metadata = {
        "source": "binance_usdm_public_api",
        "execution_compatibility": "research_proxy_only_not_okx_execution",
        "requested_start_ms": requested_start,
        "requested_end_ms": requested_end,
        "rows": len(rates),
        "first_ts": rates[0].ts if rates else None,
        "last_ts": rates[-1].ts if rates else None,
    }
    path.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _parse_utc_date(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download Binance USD-M funding history as research proxy data.")
    parser.add_argument("--symbols", nargs="+", required=True, help="Examples: BTCUSDT ETHUSDT")
    parser.add_argument("--start", default=None, help="UTC YYYY-MM-DD; defaults to --days before now")
    parser.add_argument("--end", default=None, help="UTC YYYY-MM-DD; defaults to today")
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--out", type=Path, default=Path("data/external"))
    args = parser.parse_args(argv)

    end_time = _parse_utc_date(args.end) if args.end else int(datetime.now(timezone.utc).timestamp() * 1000)
    start_time = _parse_utc_date(args.start) if args.start else int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)
    if start_time >= end_time:
        parser.error("--start must be before --end")
    complete = True
    for symbol in args.symbols:
        rates = download_history(symbol, start_time, end_time)
        path = output_path(symbol, args.out)
        save_history(path, rates, start_time, end_time)
        print(f"{symbol}: wrote {len(rates)} Binance funding rows to {path}", flush=True)
        complete = complete and bool(rates) and rates[0].ts <= start_time + 3 * 86_400_000
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
