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


OKX_HISTORY_TRADES_URL = "https://www.okx.com/api/v5/market/history-trades"


@dataclass(frozen=True, slots=True)
class TradeTick:
    symbol: str
    trade_id: str
    ts: int
    time: str
    side: str
    price: float
    size: float
    quote_volume: float


@dataclass(slots=True)
class TradeFlowFeatureBar(FeatureBar):
    active_buy_quote: float = 0.0
    active_sell_quote: float = 0.0
    active_buy_ratio: float = 0.0
    trade_flow_imbalance: float = 0.0


def fetch_trade_page(symbol: str, before: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    params = {"instId": symbol, "limit": str(limit)}
    if before is not None:
        params["before"] = before
    url = f"{OKX_HISTORY_TRADES_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX trades error for {symbol}: {payload}")
    return payload.get("data", [])


def parse_trade_rows(symbol: str, rows: list[dict[str, Any]]) -> list[TradeTick]:
    parsed: list[TradeTick] = []
    for row in rows:
        try:
            ts = int(row["ts"])
            price = float(row["px"])
            size = float(row["sz"])
            side = str(row["side"]).lower()
            if side not in ("buy", "sell"):
                continue
            parsed.append(
                TradeTick(
                    symbol=symbol,
                    trade_id=str(row["tradeId"]),
                    ts=ts,
                    time=_format_utc(ts),
                    side=side,
                    price=price,
                    size=size,
                    quote_volume=price * size,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    parsed.sort(key=lambda item: (item.ts, item.trade_id))
    return parsed


def save_trade_ticks(path: Path, ticks: list[TradeTick]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["symbol", "trade_id", "timestamp_ms", "timestamp_utc", "side", "price", "size", "quote_volume"])
        for tick in ticks:
            writer.writerow([
                tick.symbol,
                tick.trade_id,
                tick.ts,
                tick.time,
                tick.side,
                tick.price,
                tick.size,
                tick.quote_volume,
            ])


def load_trade_ticks(path: Path) -> list[TradeTick]:
    if not path.exists():
        return []
    ticks: list[TradeTick] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                ticks.append(
                    TradeTick(
                        symbol=row["symbol"],
                        trade_id=row["trade_id"],
                        ts=int(row["timestamp_ms"]),
                        time=row["timestamp_utc"],
                        side=row["side"],
                        price=float(row["price"]),
                        size=float(row["size"]),
                        quote_volume=float(row["quote_volume"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    ticks.sort(key=lambda item: (item.ts, item.trade_id))
    return ticks


def download_trade_ticks(
    symbol: str,
    out_dir: Path,
    before: str | None = None,
    limit: int = 100,
    pages: int = 1,
    sleep_seconds: float = 0.12,
) -> int:
    path = trade_ticks_output_path(symbol, out_dir)
    ticks = {tick.trade_id: tick for tick in load_trade_ticks(path)}
    cursor = before
    for page_idx in range(max(1, pages)):
        page = fetch_trade_page(symbol, before=cursor, limit=limit)
        parsed = parse_trade_rows(symbol, page)
        if not parsed:
            break
        for tick in parsed:
            ticks[tick.trade_id] = tick
        oldest_tick = min(parsed, key=lambda item: item.ts)
        if cursor is not None and oldest_tick.trade_id == cursor:
            break
        cursor = oldest_tick.trade_id
        if len(page) < limit:
            break
        if sleep_seconds > 0 and page_idx + 1 < pages:
            time.sleep(sleep_seconds)
    ordered = sorted(ticks.values(), key=lambda item: (item.ts, item.trade_id))
    save_trade_ticks(path, ordered)
    return len(ordered)


def add_trade_flow_features(bars: list[FeatureBar], ticks: list[TradeTick]) -> list[TradeFlowFeatureBar]:
    ordered_ticks = sorted(ticks, key=lambda item: (item.ts, item.trade_id))
    out: list[TradeFlowFeatureBar] = []
    tick_idx = 0

    for idx, bar in enumerate(bars):
        next_ts = bars[idx + 1].ts if idx + 1 < len(bars) else None
        active_buy_quote = 0.0
        active_sell_quote = 0.0
        while tick_idx < len(ordered_ticks) and ordered_ticks[tick_idx].ts < bar.ts:
            tick_idx += 1
        cursor = tick_idx
        while cursor < len(ordered_ticks) and (next_ts is None or ordered_ticks[cursor].ts < next_ts):
            tick = ordered_ticks[cursor]
            if tick.side == "buy":
                active_buy_quote += tick.quote_volume
            elif tick.side == "sell":
                active_sell_quote += tick.quote_volume
            cursor += 1
        tick_idx = cursor
        total = active_buy_quote + active_sell_quote
        active_buy_ratio = active_buy_quote / total if total else 0.0
        imbalance = (active_buy_quote - active_sell_quote) / total if total else 0.0
        out.append(
            TradeFlowFeatureBar(
                **{field.name: getattr(bar, field.name) for field in fields(FeatureBar)},
                active_buy_quote=active_buy_quote,
                active_sell_quote=active_sell_quote,
                active_buy_ratio=active_buy_ratio,
                trade_flow_imbalance=imbalance,
            )
        )
    return out


def trade_ticks_output_path(symbol: str, out_dir: Path) -> Path:
    return out_dir / f"{symbol}_trades.csv"


def _format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download OKX historical trades into CSV cache files.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--before")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=0.12)
    args = parser.parse_args(argv)

    for symbol in args.symbols:
        count = download_trade_ticks(
            symbol,
            out_dir=args.out,
            before=args.before,
            limit=args.limit,
            pages=args.pages,
            sleep_seconds=args.sleep,
        )
        print(f"{symbol}: wrote {count} trade rows to {trade_ticks_output_path(symbol, args.out)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
