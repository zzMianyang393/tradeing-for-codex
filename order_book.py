from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market import FeatureBar


OKX_ORDER_BOOK_URL = "https://www.okx.com/api/v5/market/books"


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    symbol: str
    ts: int
    time: str
    best_bid: float
    best_ask: float
    spread_pct: float
    bid_depth_quote: float
    ask_depth_quote: float
    depth_imbalance: float


@dataclass(slots=True)
class OrderBookFeatureBar(FeatureBar):
    best_bid: float = 0.0
    best_ask: float = 0.0
    order_book_spread_pct: float = 0.0
    bid_depth_quote: float = 0.0
    ask_depth_quote: float = 0.0
    depth_imbalance: float = 0.0


def fetch_order_book_snapshot(symbol: str, depth: int = 20) -> dict[str, Any]:
    params = {"instId": symbol, "sz": str(depth)}
    url = f"{OKX_ORDER_BOOK_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX order book error for {symbol}: {payload}")
    data = payload.get("data", [])
    return data[0] if data else {}


def parse_order_book_snapshot(symbol: str, row: dict[str, Any]) -> OrderBookSnapshot:
    ts = int(row["ts"])
    bids = _parse_levels(row.get("bids") or [])
    asks = _parse_levels(row.get("asks") or [])
    if not bids or not asks:
        raise ValueError(f"Order book snapshot for {symbol} has no bids or asks")
    best_bid = bids[0][0]
    best_ask = asks[0][0]
    mid = (best_bid + best_ask) / 2.0
    spread_pct = (best_ask - best_bid) / mid if mid else 0.0
    bid_depth_quote = sum(price * size for price, size in bids)
    ask_depth_quote = sum(price * size for price, size in asks)
    total_depth = bid_depth_quote + ask_depth_quote
    depth_imbalance = (bid_depth_quote - ask_depth_quote) / total_depth if total_depth else 0.0
    return OrderBookSnapshot(
        symbol=symbol,
        ts=ts,
        time=_format_utc(ts),
        best_bid=best_bid,
        best_ask=best_ask,
        spread_pct=spread_pct,
        bid_depth_quote=bid_depth_quote,
        ask_depth_quote=ask_depth_quote,
        depth_imbalance=depth_imbalance,
    )


def save_order_book_snapshots(path: Path, snapshots: list[OrderBookSnapshot]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "symbol",
            "timestamp_ms",
            "timestamp_utc",
            "best_bid",
            "best_ask",
            "spread_pct",
            "bid_depth_quote",
            "ask_depth_quote",
            "depth_imbalance",
        ])
        for snapshot in snapshots:
            writer.writerow([
                snapshot.symbol,
                snapshot.ts,
                snapshot.time,
                snapshot.best_bid,
                snapshot.best_ask,
                snapshot.spread_pct,
                snapshot.bid_depth_quote,
                snapshot.ask_depth_quote,
                snapshot.depth_imbalance,
            ])


def load_order_book_snapshots(path: Path) -> list[OrderBookSnapshot]:
    if not path.exists():
        return []
    snapshots: list[OrderBookSnapshot] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                snapshots.append(
                    OrderBookSnapshot(
                        symbol=row["symbol"],
                        ts=int(row["timestamp_ms"]),
                        time=row["timestamp_utc"],
                        best_bid=float(row["best_bid"]),
                        best_ask=float(row["best_ask"]),
                        spread_pct=float(row["spread_pct"]),
                        bid_depth_quote=float(row["bid_depth_quote"]),
                        ask_depth_quote=float(row["ask_depth_quote"]),
                        depth_imbalance=float(row["depth_imbalance"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    snapshots.sort(key=lambda item: item.ts)
    return snapshots


def append_order_book_snapshot(symbol: str, out_dir: Path, depth: int = 20) -> int:
    path = order_book_output_path(symbol, out_dir)
    snapshots = {snapshot.ts: snapshot for snapshot in load_order_book_snapshots(path)}
    snapshot = parse_order_book_snapshot(symbol, fetch_order_book_snapshot(symbol, depth=depth))
    snapshots[snapshot.ts] = snapshot
    ordered = [snapshots[ts] for ts in sorted(snapshots)]
    save_order_book_snapshots(path, ordered)
    return len(ordered)


def add_order_book_features(
    bars: list[FeatureBar],
    snapshots: list[OrderBookSnapshot],
) -> list[OrderBookFeatureBar]:
    ordered = sorted(snapshots, key=lambda item: item.ts)
    out: list[OrderBookFeatureBar] = []
    snapshot_idx = 0
    latest = OrderBookSnapshot("", 0, "", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    for bar in bars:
        while snapshot_idx < len(ordered) and ordered[snapshot_idx].ts <= bar.ts:
            latest = ordered[snapshot_idx]
            snapshot_idx += 1
        out.append(
            OrderBookFeatureBar(
                **{field.name: getattr(bar, field.name) for field in fields(FeatureBar)},
                best_bid=latest.best_bid,
                best_ask=latest.best_ask,
                order_book_spread_pct=latest.spread_pct,
                bid_depth_quote=latest.bid_depth_quote,
                ask_depth_quote=latest.ask_depth_quote,
                depth_imbalance=latest.depth_imbalance,
            )
        )
    return out


def order_book_output_path(symbol: str, out_dir: Path) -> Path:
    return out_dir / f"{symbol}_order_book.csv"


def _parse_levels(levels: list[list[Any]]) -> list[tuple[float, float]]:
    parsed: list[tuple[float, float]] = []
    for level in levels:
        if len(level) < 2:
            continue
        try:
            parsed.append((float(level[0]), float(level[1])))
        except (TypeError, ValueError):
            continue
    return parsed


def _format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append OKX order-book snapshots into CSV cache files.")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--depth", type=int, default=20)
    args = parser.parse_args(argv)

    for symbol in args.symbols:
        count = append_order_book_snapshot(symbol, out_dir=args.out, depth=args.depth)
        print(f"{symbol}: wrote {count} order-book rows to {order_book_output_path(symbol, args.out)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
