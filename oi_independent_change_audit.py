"""Audit independent daily OKX OI change events.

This is research infrastructure, not a strategy.  Daily OKX OI snapshots are
treated as available at 16:00 UTC; all forward returns enter at the next 15m
bar, 16:15 UTC, using OKX 15m OHLCV.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


FIFTEEN_MINUTES_MS = 15 * 60 * 1000
ROUND_TRIP_COST = 0.0016


@dataclass(frozen=True)
class OiChange:
    symbol: str
    ts: int
    timestamp_utc: str
    change_pct: float


@dataclass(frozen=True)
class PriceBar:
    ts: int
    open: float
    close: float


@dataclass(frozen=True)
class EventReturn:
    event_ts: int
    timestamp_utc: str
    event_direction: str
    symbol: str
    oi_change_pct: float
    entry_ts: int
    horizon_bars: int
    raw_return_pct: float
    long_net_pct: float
    short_net_pct: float
    split: str


def parse_timestamp_ms(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def load_oi_changes(path: Path) -> list[OiChange]:
    rows: list[tuple[int, str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                ts = int(row["ts"])
                timestamp = row["timestamp_utc"]
                value = float(row["open_interest_usd"])
            except (KeyError, TypeError, ValueError):
                continue
            if value > 0:
                rows.append((ts, timestamp, value))
    rows.sort(key=lambda item: item[0])
    symbol = path.name.replace("_open_interest_1d.csv", "")
    changes: list[OiChange] = []
    for previous, current in zip(rows, rows[1:]):
        previous_value = previous[2]
        if previous_value <= 0:
            continue
        changes.append(
            OiChange(
                symbol=symbol,
                ts=current[0],
                timestamp_utc=current[1],
                change_pct=current[2] / previous_value - 1.0,
            )
        )
    return changes


def load_price_bars(path: Path) -> dict[int, PriceBar]:
    bars: dict[int, PriceBar] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                ts = parse_timestamp_ms(row["timestamp"])
                bars[ts] = PriceBar(ts=ts, open=float(row["open"]), close=float(row["close"]))
            except (KeyError, TypeError, ValueError):
                continue
    return bars


def discover_symbols(data_dir: Path) -> list[str]:
    symbols: list[str] = []
    for path in sorted(data_dir.glob("*-USDT-SWAP_open_interest_1d.csv")):
        symbol = path.name.replace("_open_interest_1d.csv", "")
        base = symbol.split("-", 1)[0]
        if (data_dir / f"{base}_15m.csv").exists():
            symbols.append(symbol)
    return symbols


def find_sync_events(
    changes_by_symbol: dict[str, list[OiChange]],
    min_abs_change: float = 0.05,
    sync_fraction: float = 0.4,
    min_coins: int = 10,
) -> list[dict[str, Any]]:
    by_ts: dict[int, list[OiChange]] = defaultdict(list)
    for changes in changes_by_symbol.values():
        for change in changes:
            by_ts[change.ts].append(change)

    events: list[dict[str, Any]] = []
    for ts in sorted(by_ts):
        changes = by_ts[ts]
        if len(changes) < min_coins:
            continue
        up = [item for item in changes if item.change_pct >= min_abs_change]
        down = [item for item in changes if item.change_pct <= -min_abs_change]
        up_fraction = len(up) / len(changes)
        down_fraction = len(down) / len(changes)
        if up_fraction >= sync_fraction and len(up) >= len(down):
            qualified = up
            direction = "oi_up"
            event_fraction = up_fraction
        elif down_fraction >= sync_fraction:
            qualified = down
            direction = "oi_down"
            event_fraction = down_fraction
        else:
            continue
        events.append(
            {
                "event_ts": ts,
                "timestamp_utc": qualified[0].timestamp_utc,
                "event_direction": direction,
                "available_coins": len(changes),
                "qualified_coins": len(qualified),
                "qualified_fraction": event_fraction,
                "median_abs_change_pct": median([abs(item.change_pct) for item in qualified]),
                "symbols": [item.symbol for item in qualified],
                "changes": {item.symbol: item.change_pct for item in qualified},
            }
        )
    return events


def split_for_event(event_ts: int, formation_end_ts: int) -> str:
    return "formation" if event_ts <= formation_end_ts else "oos"


def compute_event_returns(
    events: list[dict[str, Any]],
    price_by_symbol: dict[str, dict[int, PriceBar]],
    formation_end_ts: int,
    horizons_bars: tuple[int, ...] = (16, 96),
    round_trip_cost: float = ROUND_TRIP_COST,
) -> list[EventReturn]:
    results: list[EventReturn] = []
    for event in events:
        entry_ts = int(event["event_ts"]) + FIFTEEN_MINUTES_MS
        split = split_for_event(int(event["event_ts"]), formation_end_ts)
        for symbol in event["symbols"]:
            bars = price_by_symbol.get(symbol, {})
            entry = bars.get(entry_ts)
            if entry is None or entry.open <= 0:
                continue
            for horizon in horizons_bars:
                exit_bar = bars.get(entry_ts + horizon * FIFTEEN_MINUTES_MS)
                if exit_bar is None:
                    continue
                raw_return = exit_bar.close / entry.open - 1.0
                results.append(
                    EventReturn(
                        event_ts=int(event["event_ts"]),
                        timestamp_utc=str(event["timestamp_utc"]),
                        event_direction=str(event["event_direction"]),
                        symbol=symbol,
                        oi_change_pct=float(event["changes"][symbol]),
                        entry_ts=entry_ts,
                        horizon_bars=horizon,
                        raw_return_pct=raw_return * 100.0,
                        long_net_pct=(raw_return - round_trip_cost) * 100.0,
                        short_net_pct=(-raw_return - round_trip_cost) * 100.0,
                        split=split,
                    )
                )
    return results


def summarize(values: list[float]) -> dict[str, float | int]:
    return {
        "observations": len(values),
        "mean_pct": mean(values) if values else 0.0,
        "median_pct": median(values) if values else 0.0,
        "win_rate": sum(value > 0 for value in values) / len(values) if values else 0.0,
    }


def summarize_returns(returns: list[EventReturn]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for split in ("formation", "oos"):
        split_returns = [item for item in returns if item.split == split]
        output[split] = {}
        for horizon in sorted({item.horizon_bars for item in split_returns}):
            horizon_returns = [item for item in split_returns if item.horizon_bars == horizon]
            output[split][f"{horizon}_bars"] = {
                "long_net": summarize([item.long_net_pct for item in horizon_returns]),
                "short_net": summarize([item.short_net_pct for item in horizon_returns]),
                "raw": summarize([item.raw_return_pct for item in horizon_returns]),
            }
    return output


def event_concentration(events: list[dict[str, Any]], formation_end_ts: int) -> dict[str, Any]:
    formation_events = [event for event in events if int(event["event_ts"]) <= formation_end_ts]
    months = Counter(str(event["timestamp_utc"])[:7] for event in formation_events)
    top_month_count = max(months.values()) if months else 0
    return {
        "formation_events": len(formation_events),
        "top_month_share": top_month_count / len(formation_events) if formation_events else 0.0,
        "events_by_month": dict(sorted(months.items())),
    }


def tradable_event_concentration(
    returns: list[EventReturn],
    formation_end_ts: int,
    horizon_bars: int = 16,
) -> dict[str, Any]:
    formation_returns = [
        item
        for item in returns
        if item.horizon_bars == horizon_bars and item.event_ts <= formation_end_ts
    ]
    event_months: dict[int, str] = {}
    for item in formation_returns:
        event_months[item.event_ts] = item.timestamp_utc[:7]
    months = Counter(event_months.values())
    top_month_count = max(months.values()) if months else 0
    return {
        "formation_events": len(event_months),
        "top_month_share": top_month_count / len(event_months) if event_months else 0.0,
        "events_by_month": dict(sorted(months.items())),
    }


def formation_verdict(summary: dict[str, Any], tradable_concentration: dict[str, Any], min_events: int = 15) -> dict[str, Any]:
    formation_4h = summary.get("formation", {}).get("16_bars", {})
    long_net = formation_4h.get("long_net", {})
    short_net = formation_4h.get("short_net", {})
    best_mean = max(float(long_net.get("mean_pct", 0.0)), float(short_net.get("mean_pct", 0.0)))
    best_win_rate = max(float(long_net.get("win_rate", 0.0)), float(short_net.get("win_rate", 0.0)))
    reasons = []
    if int(tradable_concentration["formation_events"]) < min_events:
        reasons.append("tradable formation event count below 15")
    if best_mean <= 0:
        reasons.append("best 4h net mean is not positive after cost")
    if best_win_rate < 0.55:
        reasons.append("best 4h net win rate below 55%")
    if float(tradable_concentration["top_month_share"]) > 0.30:
        reasons.append("more than 30% of tradable formation events come from one month")
    return {
        "status": "passed_formation_screen" if not reasons else "rejected",
        "eligible_for_strategy": False,
        "reasons": reasons,
    }


def run_audit(
    data_dir: Path,
    symbols: list[str],
    formation_end: str,
    min_abs_change: float,
    sync_fraction: float,
    min_coins: int,
) -> dict[str, Any]:
    changes_by_symbol = {
        symbol: load_oi_changes(data_dir / f"{symbol}_open_interest_1d.csv")
        for symbol in symbols
    }
    price_by_symbol = {
        symbol: load_price_bars(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv")
        for symbol in symbols
    }
    formation_end_ts = parse_timestamp_ms(f"{formation_end} 16:00:00")
    events = find_sync_events(changes_by_symbol, min_abs_change, sync_fraction, min_coins)
    returns = compute_event_returns(events, price_by_symbol, formation_end_ts)
    summary = summarize_returns(returns)
    concentration = event_concentration(events, formation_end_ts)
    tradable_concentration = tradable_event_concentration(returns, formation_end_ts)
    return {
        "research_id": "daily_oi_independent_change",
        "scope": "okx_daily_oi_independent_event_audit_not_strategy",
        "formation_end": formation_end,
        "event_definition": {
            "oi_available_at_utc": "16:00",
            "entry_time": "next 15m bar at 16:15 UTC",
            "min_abs_oi_change": min_abs_change,
            "sync_fraction": sync_fraction,
            "min_coins": min_coins,
            "funding_used": False,
        },
        "symbols": symbols,
        "n_symbols": len(symbols),
        "n_events": len(events),
        "event_concentration": concentration,
        "tradable_event_concentration": tradable_concentration,
        "returns": summary,
        "formation_verdict": formation_verdict(summary, tradable_concentration),
        "events": events,
        "event_preview": events[:10],
        "event_returns": [asdict(item) for item in returns],
        "return_preview": [asdict(item) for item in returns[:20]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit independent OKX daily OI change events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--formation-end", default="2025-01-08")
    parser.add_argument("--min-abs-change", type=float, default=0.05)
    parser.add_argument("--sync-fraction", type=float, default=0.4)
    parser.add_argument("--min-coins", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_oi_independent_change_audit.json"))
    args = parser.parse_args(argv)
    symbols = args.symbols or discover_symbols(args.data)
    report = run_audit(args.data, symbols, args.formation_end, args.min_abs_change, args.sync_fraction, args.min_coins)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
