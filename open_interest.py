from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market import FeatureBar


OKX_OPEN_INTEREST_HISTORY_URL = "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history"


@dataclass(frozen=True, slots=True)
class OpenInterest:
    symbol: str
    ts: int
    time: str
    open_interest: float
    open_interest_currency: float


@dataclass(slots=True)
class OpenInterestFeatureBar(FeatureBar):
    open_interest: float = 0.0
    open_interest_currency: float = 0.0
    open_interest_change_pct: float = 0.0
    open_interest_ma: float = 0.0


def fetch_open_interest_history(
    symbol: str,
    period: str = "15m",
    limit: int = 100,
) -> list[dict[str, Any]]:
    params = {
        "instType": "SWAP",
        "instId": symbol,
        "period": period,
        "limit": str(limit),
    }
    url = f"{OKX_OPEN_INTEREST_HISTORY_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OKX open interest HTTP {exc.code} for {symbol}: {body}") from exc
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX open interest error for {symbol}: {payload}")
    return payload.get("data", [])


def parse_open_interest_rows(symbol: str, rows: list[dict[str, Any]]) -> list[OpenInterest]:
    parsed: list[OpenInterest] = []
    for row in rows:
        try:
            if isinstance(row, dict):
                ts = int(row["ts"])
                open_interest = float(row.get("oi") or 0.0)
                open_interest_currency = float(row.get("oiCcy") or 0.0)
            else:
                ts = int(row[0])
                open_interest = float(row[1])
                open_interest_currency = float(row[2])
            parsed.append(
                OpenInterest(
                    symbol=symbol,
                    ts=ts,
                    time=_format_utc(ts),
                    open_interest=open_interest,
                    open_interest_currency=open_interest_currency,
                )
            )
        except (IndexError, KeyError, TypeError, ValueError):
            continue
    parsed.sort(key=lambda item: item.ts)
    return parsed


def save_open_interest(path: Path, items: list[OpenInterest]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["symbol", "timestamp_ms", "timestamp_utc", "open_interest", "open_interest_currency"])
        for item in items:
            writer.writerow([
                item.symbol,
                item.ts,
                item.time,
                item.open_interest,
                item.open_interest_currency,
            ])


def load_open_interest(path: Path) -> list[OpenInterest]:
    if not path.exists():
        return []
    items: list[OpenInterest] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                items.append(
                    OpenInterest(
                        symbol=row["symbol"],
                        ts=int(row["timestamp_ms"]),
                        time=row["timestamp_utc"],
                        open_interest=float(row["open_interest"]),
                        open_interest_currency=float(row["open_interest_currency"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    items.sort(key=lambda item: item.ts)
    return items


def download_open_interest(
    symbol: str,
    days: int,
    out_dir: Path,
    period: str = "15m",
    limit: int = 100,
) -> int:
    path = open_interest_output_path(symbol, out_dir)
    rows = {item.ts: item for item in load_open_interest(path)}
    page = fetch_open_interest_history(symbol, period=period, limit=limit)
    for item in parse_open_interest_rows(symbol, page):
        rows[item.ts] = item
    cutoff = _cutoff_ts(rows, days)
    ordered = [
        rows[ts]
        for ts in sorted(rows)
        if cutoff is None or ts >= cutoff
    ]
    save_open_interest(path, ordered)
    return len(ordered)


def add_open_interest_features(
    bars: list[FeatureBar],
    items: list[OpenInterest],
    ma_window: int = 20,
) -> list[OpenInterestFeatureBar]:
    ordered_items = sorted(items, key=lambda item: item.ts)
    out: list[OpenInterestFeatureBar] = []
    item_idx = 0
    latest_open_interest = 0.0
    latest_open_interest_currency = 0.0
    previous_open_interest = 0.0
    seen_open_interest: list[float] = []

    for bar in bars:
        while item_idx < len(ordered_items) and ordered_items[item_idx].ts <= bar.ts:
            previous_open_interest = latest_open_interest
            latest_open_interest = ordered_items[item_idx].open_interest
            latest_open_interest_currency = ordered_items[item_idx].open_interest_currency
            seen_open_interest.append(latest_open_interest)
            item_idx += 1
        recent = seen_open_interest[-ma_window:]
        open_interest_ma = sum(recent) / len(recent) if recent else 0.0
        if previous_open_interest > 0 and latest_open_interest > 0:
            change_pct = latest_open_interest / previous_open_interest - 1.0
        else:
            change_pct = 0.0
        out.append(
            OpenInterestFeatureBar(
                **{field.name: getattr(bar, field.name) for field in fields(FeatureBar)},
                open_interest=latest_open_interest,
                open_interest_currency=latest_open_interest_currency,
                open_interest_change_pct=change_pct,
                open_interest_ma=open_interest_ma,
            )
        )
    return out


def open_interest_output_path(symbol: str, out_dir: Path) -> Path:
    return out_dir / f"{symbol}_open_interest.csv"


def _cutoff_ts(rows: dict[int, OpenInterest], days: int) -> int | None:
    if not rows or days <= 0:
        return None
    return max(rows) - days * 24 * 60 * 60 * 1000


def _format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download OKX open-interest history into CSV cache files.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--period", default="15m")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)

    for symbol in args.symbols:
        count = download_open_interest(
            symbol,
            days=args.days,
            out_dir=args.out,
            period=args.period,
            limit=args.limit,
        )
        print(f"{symbol}: wrote {count} open-interest rows to {open_interest_output_path(symbol, args.out)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
