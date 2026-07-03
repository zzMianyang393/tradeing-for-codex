from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


OKX_HISTORY_URL = "https://www.okx.com/api/v5/market/history-candles"
BAR_ROWS_PER_DAY = {
    "1m": 24 * 60,
    "3m": 24 * 20,
    "5m": 24 * 12,
    "15m": 24 * 4,
    "30m": 24 * 2,
    "1H": 24,
    "1h": 24,
    "4H": 6,
    "4h": 6,
    "1D": 1,
    "1d": 1,
}


def fetch_page(symbol: str, bar: str, after: int | None = None, limit: int = 100) -> list[list[str]]:
    params = {"instId": symbol, "bar": bar, "limit": str(limit)}
    if after is not None:
        params["after"] = str(after)
    url = f"{OKX_HISTORY_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX error for {symbol}: {payload}")
    return payload.get("data", [])


def base_symbol(symbol: str) -> str:
    return symbol.replace("-USDT-SWAP", "")


def rows_per_day(bar: str) -> int:
    if bar not in BAR_ROWS_PER_DAY:
        raise ValueError(f"Unsupported bar {bar!r}; add it to BAR_ROWS_PER_DAY first")
    return BAR_ROWS_PER_DAY[bar]


def bar_ms(bar: str) -> int:
    return int(86_400_000 / rows_per_day(bar))


def output_path(symbol: str, out_dir: Path, bar: str) -> Path:
    if bar == "1m":
        return out_dir / f"{symbol}_{bar}.csv"
    return out_dir / f"{base_symbol(symbol)}_{bar}.csv"


def fetch_page_with_retry(symbol: str, bar: str, after: int | None, limit: int, retries: int) -> list[list[str]]:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fetch_page(symbol, bar, after=after, limit=limit)
        except Exception as exc:  # pragma: no cover - live network defense
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError(f"Failed to fetch {symbol} {bar} after {retries + 1} attempts: {last_error}")


def write_rows(path: Path, ordered: list[list[str]], bar: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if bar == "1m":
            writer.writerow(
                [
                    "timestamp_ms",
                    "timestamp_utc",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume_contracts",
                    "volume_base",
                    "volume_quote",
                ]
            )
            for item in ordered:
                ts = int(item[0])
                writer.writerow(
                    [
                        ts,
                        datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                        item[1],
                        item[2],
                        item[3],
                        item[4],
                        item[5],
                        item[6] if len(item) > 6 else "",
                        item[7] if len(item) > 7 else "",
                    ]
                )
            return

        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for item in ordered:
            ts = int(item[0])
            volume = item[6] if len(item) > 6 else item[5]
            writer.writerow(
                [
                    datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    item[1],
                    item[2],
                    item[3],
                    item[4],
                    volume,
                ]
            )


def parse_timestamp_ms(value: str) -> int:
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)
    parsed = datetime.strptime(stripped, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def read_existing_rows(path: Path, bar: str) -> dict[int, list[str]]:
    if not path.exists():
        return {}
    rows: dict[int, list[str]] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            timestamp_value = row.get("timestamp_ms") or row.get("timestamp")
            if not timestamp_value:
                continue
            ts = parse_timestamp_ms(timestamp_value)
            item = [
                str(ts),
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row.get("volume_contracts") or row.get("volume") or "0",
                row.get("volume_base") or row.get("volume") or "0",
                row.get("volume_quote") or "0",
            ]
            rows[ts] = item
    if rows:
        print(f"Resuming {path.name}: loaded {len(rows)} existing rows", flush=True)
    return rows


def download_symbol(
    symbol: str,
    days: int,
    out_dir: Path,
    bar: str = "1m",
    sleep_seconds: float = 0.12,
    limit: int = 100,
    retries: int = 4,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    target_rows = days * rows_per_day(bar)
    path = output_path(symbol, out_dir, bar)
    rows: dict[int, list[str]] = read_existing_rows(path, bar)
    existing_newest = max(rows) if rows else None
    after: int | None = None
    pages = 0
    while existing_newest is not None:
        page = fetch_page_with_retry(symbol, bar, after=after, limit=limit, retries=retries)
        if not page:
            break
        pages += 1
        for item in page:
            rows[int(item[0])] = item
        oldest = min(int(item[0]) for item in page)
        after = oldest
        if pages == 1 or pages % 25 == 0:
            oldest_text = datetime.fromtimestamp(oldest / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            print(f"{symbol} {bar}: refreshed {len(rows)} rows, oldest new page {oldest_text}", flush=True)
        if oldest <= existing_newest + bar_ms(bar):
            break
        time.sleep(sleep_seconds)

    after = min(rows) if rows else None
    while len(rows) < target_rows:
        page = fetch_page_with_retry(symbol, bar, after=after, limit=limit, retries=retries)
        if not page:
            break
        pages += 1
        for item in page:
            ts = int(item[0])
            rows[ts] = item
        oldest = min(int(item[0]) for item in page)
        after = oldest
        if pages == 1 or pages % 25 == 0:
            oldest_text = datetime.fromtimestamp(oldest / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            print(f"{symbol} {bar}: {len(rows)}/{target_rows} rows, oldest {oldest_text}", flush=True)
        if pages % 50 == 0:
            write_rows(path, [rows[ts] for ts in sorted(rows)], bar)
        time.sleep(sleep_seconds)
    ordered = [rows[ts] for ts in sorted(rows)]
    write_rows(path, ordered, bar)
    return len(ordered)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download OKX historical candles into Tradering CSV format.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--out", type=Path, default=Path("../okx_historical_data/okx_historical_data"))
    parser.add_argument("--bar", default="1m")
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--retries", type=int, default=4)
    args = parser.parse_args()

    for symbol in args.symbols:
        count = download_symbol(
            symbol,
            args.days,
            args.out,
            args.bar,
            sleep_seconds=args.sleep,
            limit=args.limit,
            retries=args.retries,
        )
        print(f"{symbol}: wrote {count} rows to {output_path(symbol, args.out, args.bar)}", flush=True)


if __name__ == "__main__":
    main()
