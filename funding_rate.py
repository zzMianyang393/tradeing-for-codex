from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market import FeatureBar


OKX_FUNDING_HISTORY_URL = "https://www.okx.com/api/v5/public/funding-rate-history"
FUNDING_ROWS_PER_DAY = 3


@dataclass(frozen=True, slots=True)
class FundingRate:
    symbol: str
    ts: int
    time: str
    funding_rate: float
    realized_rate: float


@dataclass(slots=True)
class FundingFeatureBar(FeatureBar):
    funding_rate: float = 0.0
    funding_realized_rate: float = 0.0
    funding_rate_ma: float = 0.0


def fetch_funding_page(
    symbol: str,
    before: int | None = None,
    after: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    params = {"instId": symbol, "limit": str(limit)}
    if before is not None:
        params["before"] = str(before)
    if after is not None:
        params["after"] = str(after)
    url = f"{OKX_FUNDING_HISTORY_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX funding error for {symbol}: {payload}")
    return payload.get("data", [])


def parse_funding_rows(rows: list[dict[str, Any]]) -> list[FundingRate]:
    parsed: list[FundingRate] = []
    for row in rows:
        try:
            ts = int(row["fundingTime"])
            parsed.append(
                FundingRate(
                    symbol=str(row["instId"]),
                    ts=ts,
                    time=_format_utc(ts),
                    funding_rate=float(row.get("fundingRate") or 0.0),
                    realized_rate=float(row.get("realizedRate") or row.get("fundingRate") or 0.0),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    parsed.sort(key=lambda item: item.ts)
    return parsed


def save_funding_rates(path: Path, rates: list[FundingRate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["symbol", "timestamp_ms", "timestamp_utc", "funding_rate", "realized_rate"])
        for rate in rates:
            writer.writerow([rate.symbol, rate.ts, rate.time, rate.funding_rate, rate.realized_rate])


def load_funding_rates(path: Path) -> list[FundingRate]:
    if not path.exists():
        return []
    rates: list[FundingRate] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                rates.append(
                    FundingRate(
                        symbol=row["symbol"],
                        ts=int(row["timestamp_ms"]),
                        time=row["timestamp_utc"],
                        funding_rate=float(row["funding_rate"]),
                        realized_rate=float(row["realized_rate"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    rates.sort(key=lambda item: item.ts)
    return rates


def download_funding_rates(
    symbol: str,
    days: int,
    out_dir: Path,
    sleep_seconds: float = 0.12,
    retry_sleep_seconds: float = 1.0,
    retries: int = 4,
    limit: int = 100,
) -> int:
    path = funding_output_path(symbol, out_dir)
    rows = {rate.ts: rate for rate in load_funding_rates(path)}
    target_rows = max(1, days * FUNDING_ROWS_PER_DAY)
    after = min(rows) if rows else None

    while len(rows) < target_rows:
        page = _fetch_funding_page_with_retry(
            symbol,
            after=after,
            limit=limit,
            retries=retries,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        if not page:
            break
        parsed = parse_funding_rows(page)
        if not parsed:
            break
        for rate in parsed:
            rows[rate.ts] = rate
        oldest = min(rate.ts for rate in parsed)
        if after is not None and oldest >= after:
            break
        after = oldest
        if sleep_seconds > 0 and len(rows) < target_rows:
            time.sleep(sleep_seconds)

    ordered = [rows[ts] for ts in sorted(rows)]
    save_funding_rates(path, ordered)
    return len(ordered)


def _fetch_funding_page_with_retry(
    symbol: str,
    before: int | None = None,
    after: int | None = None,
    limit: int = 100,
    retries: int = 4,
    retry_sleep_seconds: float = 1.0,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fetch_funding_page(symbol, before=before, after=after, limit=limit)
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            if retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds)
    raise RuntimeError(f"Failed to fetch funding rates for {symbol}: {last_error}")


def add_funding_features(bars: list[FeatureBar], rates: list[FundingRate], ma_window: int = 7) -> list[FundingFeatureBar]:
    ordered_rates = sorted(rates, key=lambda item: item.ts)
    out: list[FundingFeatureBar] = []
    rate_idx = 0
    latest_rate = 0.0
    latest_realized_rate = 0.0
    seen_rates: list[float] = []

    for bar in bars:
        while rate_idx < len(ordered_rates) and ordered_rates[rate_idx].ts <= bar.ts:
            latest_rate = ordered_rates[rate_idx].funding_rate
            latest_realized_rate = ordered_rates[rate_idx].realized_rate
            seen_rates.append(latest_rate)
            rate_idx += 1
        recent = seen_rates[-ma_window:]
        funding_rate_ma = sum(recent) / len(recent) if recent else 0.0
        out.append(
            FundingFeatureBar(
                **{field.name: getattr(bar, field.name) for field in fields(FeatureBar)},
                funding_rate=latest_rate,
                funding_realized_rate=latest_realized_rate,
                funding_rate_ma=funding_rate_ma,
            )
        )
    return out


def funding_output_path(symbol: str, out_dir: Path) -> Path:
    return out_dir / f"{symbol}_funding.csv"


def _format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download OKX funding-rate history into CSV cache files.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--retry-sleep", type=float, default=1.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)

    incomplete = False
    target_rows = max(1, args.days * FUNDING_ROWS_PER_DAY)
    for symbol in args.symbols:
        count = download_funding_rates(
            symbol,
            days=args.days,
            out_dir=args.out,
            sleep_seconds=args.sleep,
            retry_sleep_seconds=args.retry_sleep,
            retries=args.retries,
            limit=args.limit,
        )
        print(f"{symbol}: wrote {count} funding rows to {funding_output_path(symbol, args.out)}", flush=True)
        if count < target_rows:
            print(
                f"{symbol}: ERROR incomplete history ({count}/{target_rows} rows)",
                flush=True,
            )
            incomplete = True
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
