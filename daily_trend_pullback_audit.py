"""Daily trend-pullback audit.

Research-only rule:

  - use completed daily candles
  - require EMA50 > EMA200 as the long-trend context
  - go long when close is below EMA20 inside that trend
  - enter on the next daily open
  - exit on the next daily open after close recovers to EMA20, or after 15 days
  - one position per symbol; signals while a position is open are skipped
  - 0.16% single-market round-trip cost

No parameter scan is performed.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

from daily_ma_alignment_audit import (
    DAY_MS,
    PriceBar,
    ema_values,
    format_utc,
    load_daily_for_base,
    parse_timestamp_ms,
)


EMA_FAST = 20
EMA_CONTEXT = 50
EMA_SLOW = 200
MAX_HOLD_DAYS = 15
ROUND_TRIP_COST = 0.0016


@dataclass(frozen=True)
class PullbackSignal:
    symbol: str
    signal_ts: int
    signal_timestamp_utc: str
    split: str
    close: float
    ema_fast: float
    ema_context: float
    ema_slow: float


@dataclass(frozen=True)
class TradeEvent:
    symbol: str
    direction: str
    split: str
    signal_ts: int
    signal_timestamp_utc: str
    entry_ts: int
    entry_timestamp_utc: str
    exit_ts: int
    exit_timestamp_utc: str
    exit_reason: str
    entry_price: float
    exit_price: float
    gross_return_pct: float
    net_return_pct: float
    hold_days: int


def discover_bases(data_dir: Path) -> list[str]:
    return sorted(path.name.removesuffix("_15m.csv") for path in data_dir.glob("*_15m.csv"))


def split_for_signal(signal_ts: int, formation_start_ts: int, formation_end_ts: int, oos_end_ts: int) -> str | None:
    if formation_start_ts <= signal_ts <= formation_end_ts:
        return "formation"
    if formation_end_ts < signal_ts <= oos_end_ts:
        return "oos"
    return None


def generate_signals(
    symbol: str,
    daily: list[PriceBar],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[PullbackSignal]:
    closes = [bar.close for bar in daily]
    fast = ema_values(closes, EMA_FAST)
    context = ema_values(closes, EMA_CONTEXT)
    slow = ema_values(closes, EMA_SLOW)
    signals: list[PullbackSignal] = []
    for index in range(EMA_SLOW, len(daily) - 1):
        if fast[index] is None or context[index] is None or slow[index] is None:
            continue
        if not (context[index] > slow[index] and daily[index].close < fast[index]):
            continue
        signal_ts = daily[index].ts + DAY_MS
        split = split_for_signal(signal_ts, formation_start_ts, formation_end_ts, oos_end_ts)
        if split is None:
            continue
        signals.append(
            PullbackSignal(
                symbol=symbol,
                signal_ts=signal_ts,
                signal_timestamp_utc=format_utc(signal_ts),
                split=split,
                close=round(daily[index].close, 10),
                ema_fast=round(float(fast[index]), 10),
                ema_context=round(float(context[index]), 10),
                ema_slow=round(float(slow[index]), 10),
            )
        )
    return signals


def first_bar_at_or_after(daily: list[PriceBar], ts: int, start_index: int = 0) -> int | None:
    for index in range(start_index, len(daily)):
        if daily[index].ts >= ts:
            return index
    return None


def find_exit_index(daily: list[PriceBar], entry_index: int) -> tuple[int | None, str]:
    fast = ema_values([bar.close for bar in daily], EMA_FAST)
    final_signal_index = min(entry_index + MAX_HOLD_DAYS - 1, len(daily) - 2)
    if final_signal_index < entry_index:
        return None, "open_position_no_exit"
    for signal_index in range(entry_index, final_signal_index + 1):
        if fast[signal_index] is not None and daily[signal_index].close >= fast[signal_index]:
            return signal_index + 1, "ema20_recovery"
    return final_signal_index + 1, "time"


def simulate_trade(signal: PullbackSignal, daily: list[PriceBar], entry_index: int) -> TradeEvent | None:
    if entry_index >= len(daily):
        return None
    exit_index, exit_reason = find_exit_index(daily, entry_index)
    if exit_index is None or exit_index >= len(daily):
        return None
    entry = daily[entry_index]
    exit_bar = daily[exit_index]
    if entry.open <= 0:
        return None
    gross = exit_bar.open / entry.open - 1.0
    net = gross - ROUND_TRIP_COST
    return TradeEvent(
        symbol=signal.symbol,
        direction="long",
        split=signal.split,
        signal_ts=signal.signal_ts,
        signal_timestamp_utc=signal.signal_timestamp_utc,
        entry_ts=entry.ts,
        entry_timestamp_utc=entry.timestamp_utc,
        exit_ts=exit_bar.ts,
        exit_timestamp_utc=exit_bar.timestamp_utc,
        exit_reason=exit_reason,
        entry_price=round(entry.open, 10),
        exit_price=round(exit_bar.open, 10),
        gross_return_pct=round(gross * 100.0, 6),
        net_return_pct=round(net * 100.0, 6),
        hold_days=exit_index - entry_index,
    )


def audit_symbol(
    symbol: str,
    daily: list[PriceBar],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[TradeEvent]:
    events: list[TradeEvent] = []
    next_available_ts = 0
    start_index = 0
    for signal in generate_signals(symbol, daily, formation_start_ts, formation_end_ts, oos_end_ts):
        if signal.signal_ts < next_available_ts:
            continue
        entry_index = first_bar_at_or_after(daily, signal.signal_ts, start_index)
        if entry_index is None:
            continue
        trade = simulate_trade(signal, daily, entry_index)
        if trade is None or trade.exit_ts > oos_end_ts:
            continue
        events.append(trade)
        next_available_ts = trade.exit_ts + DAY_MS
        start_index = entry_index
    return events


def summarize(values: list[float]) -> dict[str, float | int]:
    positives = [value for value in values if value > 0]
    negatives = [value for value in values if value <= 0]
    gross_profit = sum(positives)
    gross_loss = abs(sum(negatives))
    return {
        "observations": len(values),
        "sum_pct": round(sum(values), 6) if values else 0.0,
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "median_pct": round(median(values), 6) if values else 0.0,
        "win_rate": round(len(positives) / len(values), 6) if values else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
    }


def summarize_events(events: list[TradeEvent]) -> dict[str, Any]:
    return {split: summarize([event.net_return_pct for event in events if event.split == split]) for split in ("formation", "oos")}


def concentration(events: list[TradeEvent], split: str) -> dict[str, Any]:
    split_events = [event for event in events if event.split == split]
    months = Counter(event.signal_timestamp_utc[:7] for event in split_events)
    symbols = Counter(event.symbol for event in split_events)
    positive_by_month: Counter[str] = Counter()
    for event in split_events:
        if event.net_return_pct > 0:
            positive_by_month[event.signal_timestamp_utc[:7]] += event.net_return_pct
    total_positive = sum(positive_by_month.values())
    top_month_positive = max(positive_by_month.values()) if positive_by_month else 0.0
    return {
        "events": len(split_events),
        "top_month_event_share": round(max(months.values()) / len(split_events), 6) if split_events else 0.0,
        "top_symbol_event_share": round(max(symbols.values()) / len(split_events), 6) if split_events else 0.0,
        "top_month_positive_contribution_share": round(top_month_positive / total_positive, 6) if total_positive > 0 else 0.0,
        "events_by_month": dict(sorted(months.items())),
        "events_by_symbol": dict(sorted(symbols.items())),
    }


def verdict(summary: dict[str, Any], formation_concentration: dict[str, Any], oos_concentration: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    formation = summary["formation"]
    oos = summary["oos"]
    if int(formation["observations"]) < 20:
        reasons.append(f"formation events {formation['observations']} < 20")
    if float(formation["sum_pct"]) <= 0:
        reasons.append(f"formation net sum {formation['sum_pct']:+.6f}% <= 0")
    if float(oos["sum_pct"]) <= 0:
        reasons.append(f"oos net sum {oos['sum_pct']:+.6f}% <= 0")
    if float(formation_concentration["top_month_positive_contribution_share"]) > 0.25:
        reasons.append(
            "formation top month positive contribution "
            f"{formation_concentration['top_month_positive_contribution_share']:.2%} > 25%"
        )
    if float(oos_concentration["top_month_positive_contribution_share"]) > 0.25:
        reasons.append(
            "oos top month positive contribution "
            f"{oos_concentration['top_month_positive_contribution_share']:.2%} > 25%"
        )
    return {"status": "rejected" if reasons else "passed_research_screen", "eligible_for_strategy": False, "reasons": reasons}


def run_audit(
    data_dir: Path,
    bases: list[str],
    formation_start: str,
    formation_end: str,
    oos_end: str,
) -> dict[str, Any]:
    formation_start_ts = parse_timestamp_ms(formation_start)
    formation_end_ts = parse_timestamp_ms(f"{formation_end} 23:59:59")
    oos_end_ts = parse_timestamp_ms(f"{oos_end} 23:59:59")
    events: list[TradeEvent] = []
    data_sources: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for base in bases:
        daily, source = load_daily_for_base(data_dir, base)
        data_sources[base] = source
        if not daily:
            skipped[base] = source
            continue
        if len(daily) < EMA_SLOW + MAX_HOLD_DAYS + 30:
            skipped[base] = "insufficient_daily_history"
            continue
        events.extend(audit_symbol(f"{base}-USDT-SWAP", daily, formation_start_ts, formation_end_ts, oos_end_ts))
    summary = summarize_events(events)
    formation_concentration = concentration(events, "formation")
    oos_concentration = concentration(events, "oos")
    return {
        "research_id": "daily_trend_pullback",
        "scope": "event_audit_not_strategy",
        "parameters": {
            "ema_fast": EMA_FAST,
            "ema_context": EMA_CONTEXT,
            "ema_slow": EMA_SLOW,
            "max_hold_days": MAX_HOLD_DAYS,
            "round_trip_cost": ROUND_TRIP_COST,
            "entry": "next daily open after completed EMA50 > EMA200 and close < EMA20",
            "exit": "next daily open after close recovers to EMA20, or 15-day time exit",
            "overlap_rule": "one open event per symbol; signals during an open event are skipped",
        },
        "formation_period": f"{formation_start} to {formation_end}",
        "oos_period": f"2025-01-01 to {oos_end}",
        "bases": bases,
        "data_sources": data_sources,
        "skipped_symbols": skipped,
        "summary": summary,
        "formation_concentration": formation_concentration,
        "oos_concentration": oos_concentration,
        "formation_verdict": verdict(summary, formation_concentration, oos_concentration),
        "events": [asdict(event) for event in events],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit daily trend-pullback events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--bases", nargs="+")
    parser.add_argument("--formation-start", default="2024-01-01")
    parser.add_argument("--formation-end", default="2024-12-31")
    parser.add_argument("--oos-end", default="2025-07-10")
    parser.add_argument("--out", type=Path, default=Path("reports/daily_trend_pullback_audit.json"))
    args = parser.parse_args(argv)
    bases = args.bases or discover_bases(args.data)
    report = run_audit(args.data, bases, args.formation_start, args.formation_end, args.oos_end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
