"""Daily MA alignment trend audit.

This is research infrastructure, not a runnable strategy.  It implements one
pre-registered low-turnover representative rule:

  - use completed daily candles
  - go long when EMA20 > EMA50 > EMA200 after the daily close
  - enter on the next daily open
  - exit on the next daily open after EMA20 <= EMA50
  - one position per symbol; signals while a position is open are skipped
  - 0.16% single-market round-trip cost

No parameter scan is performed.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


DAY_MS = 24 * 60 * 60 * 1000
EMA_FAST = 20
EMA_MID = 50
EMA_SLOW = 200
ROUND_TRIP_COST = 0.0016
NOV_2024 = "2024-11"


@dataclass(frozen=True)
class PriceBar:
    ts: int
    timestamp_utc: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class AlignmentSignal:
    symbol: str
    signal_ts: int
    signal_timestamp_utc: str
    split: str
    close: float
    ema_fast: float
    ema_mid: float
    ema_slow: float


@dataclass(frozen=True)
class TradeEvent:
    symbol: str
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


def parse_timestamp_ms(value: str) -> int:
    stripped = value.strip()
    if stripped.isdigit():
        raw = int(stripped)
        return raw * 1000 if raw < 10_000_000_000 else raw
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(stripped, fmt).replace(tzinfo=timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(f"unsupported timestamp: {value!r}")


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load_ohlcv(path: Path) -> list[PriceBar]:
    bars: list[PriceBar] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                raw_ts = row.get("timestamp_ms") or row.get("timestamp") or row.get("time")
                if raw_ts is None:
                    continue
                ts = parse_timestamp_ms(raw_ts)
                bars.append(
                    PriceBar(
                        ts=ts,
                        timestamp_utc=format_utc(ts),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0.0),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    bars.sort(key=lambda bar: bar.ts)
    return bars


def resample_daily(bars: list[PriceBar]) -> list[PriceBar]:
    buckets: dict[int, list[PriceBar]] = {}
    for bar in bars:
        day_ts = (bar.ts // DAY_MS) * DAY_MS
        buckets.setdefault(day_ts, []).append(bar)

    daily: list[PriceBar] = []
    for day_ts in sorted(buckets):
        group = sorted(buckets[day_ts], key=lambda item: item.ts)
        daily.append(
            PriceBar(
                ts=day_ts,
                timestamp_utc=format_utc(day_ts),
                open=group[0].open,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=group[-1].close,
                volume=sum(item.volume for item in group),
            )
        )
    return daily


def load_daily_for_base(data_dir: Path, base: str) -> tuple[list[PriceBar], str]:
    daily_path = data_dir / f"{base}_1d.csv"
    if daily_path.exists():
        return load_ohlcv(daily_path), "native_1d"

    for timeframe in ("4h", "1h", "15m"):
        path = data_dir / f"{base}_{timeframe}.csv"
        if path.exists():
            return resample_daily(load_ohlcv(path)), f"resampled_from_{timeframe}"
    return [], "missing_ohlcv"


def ema_values(values: list[float], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    result: list[float | None] = []
    alpha = 2.0 / (period + 1.0)
    ema: float | None = None
    for index, value in enumerate(values):
        if index + 1 < period:
            result.append(None)
            continue
        if index + 1 == period:
            ema = sum(values[:period]) / period
        else:
            assert ema is not None
            ema = value * alpha + ema * (1.0 - alpha)
        result.append(ema)
    return result


def split_for_signal(signal_ts: int, formation_start_ts: int, formation_end_ts: int, oos_end_ts: int) -> str | None:
    if formation_start_ts <= signal_ts <= formation_end_ts:
        return "formation"
    if formation_end_ts < signal_ts <= oos_end_ts:
        return "oos"
    return None


def alignment_at(ema_fast: float | None, ema_mid: float | None, ema_slow: float | None) -> bool:
    return (
        ema_fast is not None
        and ema_mid is not None
        and ema_slow is not None
        and ema_fast > ema_mid > ema_slow
    )


def generate_signals(
    symbol: str,
    daily: list[PriceBar],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[AlignmentSignal]:
    closes = [bar.close for bar in daily]
    fast_values = ema_values(closes, EMA_FAST)
    mid_values = ema_values(closes, EMA_MID)
    slow_values = ema_values(closes, EMA_SLOW)
    signals: list[AlignmentSignal] = []
    previous_aligned = False

    for index in range(len(daily) - 1):
        aligned = alignment_at(fast_values[index], mid_values[index], slow_values[index])
        if not aligned:
            previous_aligned = False
            continue
        if previous_aligned:
            continue
        signal_ts = daily[index].ts + DAY_MS
        split = split_for_signal(signal_ts, formation_start_ts, formation_end_ts, oos_end_ts)
        if split is None:
            previous_aligned = True
            continue
        signals.append(
            AlignmentSignal(
                symbol=symbol,
                signal_ts=signal_ts,
                signal_timestamp_utc=format_utc(signal_ts),
                split=split,
                close=round(daily[index].close, 10),
                ema_fast=round(float(fast_values[index]), 10),
                ema_mid=round(float(mid_values[index]), 10),
                ema_slow=round(float(slow_values[index]), 10),
            )
        )
        previous_aligned = True
    return signals


def first_bar_at_or_after(daily: list[PriceBar], ts: int, start_index: int = 0) -> int | None:
    for index in range(start_index, len(daily)):
        if daily[index].ts >= ts:
            return index
    return None


def find_exit_index(daily: list[PriceBar], entry_index: int) -> tuple[int | None, str]:
    closes = [bar.close for bar in daily]
    fast_values = ema_values(closes, EMA_FAST)
    mid_values = ema_values(closes, EMA_MID)
    for signal_index in range(entry_index, len(daily) - 1):
        fast = fast_values[signal_index]
        mid = mid_values[signal_index]
        if fast is not None and mid is not None and fast <= mid:
            return signal_index + 1, "ema20_cross_under_ema50"
    return None, "open_position_no_exit"


def simulate_trade(signal: AlignmentSignal, daily: list[PriceBar], entry_index: int) -> TradeEvent | None:
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
    signals = generate_signals(symbol, daily, formation_start_ts, formation_end_ts, oos_end_ts)
    events: list[TradeEvent] = []
    next_available_ts = 0
    start_index = 0
    for signal in signals:
        if signal.signal_ts < next_available_ts:
            continue
        entry_index = first_bar_at_or_after(daily, signal.signal_ts, start_index)
        if entry_index is None:
            continue
        trade = simulate_trade(signal, daily, entry_index)
        if trade is None:
            continue
        if trade.exit_ts > oos_end_ts:
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


def summarize_events(events: list[TradeEvent], excluded_month: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split in ("formation", "oos"):
        split_events = [
            event
            for event in events
            if event.split == split and (excluded_month is None or event.signal_timestamp_utc[:7] != excluded_month)
        ]
        result[split] = summarize([event.net_return_pct for event in split_events])
    return result


def concentration(events: list[TradeEvent], split: str) -> dict[str, Any]:
    split_events = [event for event in events if event.split == split]
    months = Counter(event.signal_timestamp_utc[:7] for event in split_events)
    symbols = Counter(event.symbol for event in split_events)
    positive_by_month: Counter[str] = Counter()
    for event in split_events:
        if event.net_return_pct > 0:
            positive_by_month[event.signal_timestamp_utc[:7]] += event.net_return_pct
    top_month_events = max(months.values()) if months else 0
    top_symbol_events = max(symbols.values()) if symbols else 0
    total_positive = sum(positive_by_month.values())
    top_month_positive = max(positive_by_month.values()) if positive_by_month else 0.0
    return {
        "events": len(split_events),
        "top_month_event_share": round(top_month_events / len(split_events), 6) if split_events else 0.0,
        "top_symbol_event_share": round(top_symbol_events / len(split_events), 6) if split_events else 0.0,
        "top_month_positive_contribution_share": round(top_month_positive / total_positive, 6) if total_positive > 0 else 0.0,
        "events_by_month": dict(sorted(months.items())),
        "events_by_symbol": dict(sorted(symbols.items())),
    }


def verdict(
    summary: dict[str, Any],
    without_nov_2024: dict[str, Any],
    formation_concentration: dict[str, Any],
    oos_concentration: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    formation = summary["formation"]
    oos = summary["oos"]
    formation_ex_nov = without_nov_2024["formation"]
    if int(formation["observations"]) < 8:
        reasons.append(f"formation events {formation['observations']} < 8")
    if float(formation["sum_pct"]) <= 0:
        reasons.append(f"formation net sum {formation['sum_pct']:+.6f}% <= 0")
    if float(oos["sum_pct"]) <= 0:
        reasons.append(f"oos net sum {oos['sum_pct']:+.6f}% <= 0")
    if float(formation_ex_nov["sum_pct"]) <= 0:
        reasons.append(f"formation net sum excluding 2024-11 {formation_ex_nov['sum_pct']:+.6f}% <= 0")
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
    status = "rejected" if reasons else "passed_research_screen"
    return {
        "status": status,
        "eligible_for_strategy": False,
        "reasons": reasons,
    }


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
        if len(daily) < EMA_SLOW + EMA_MID + 5:
            skipped[base] = "insufficient_daily_history"
            continue
        events.extend(audit_symbol(f"{base}-USDT-SWAP", daily, formation_start_ts, formation_end_ts, oos_end_ts))

    summary = summarize_events(events)
    without_nov_2024 = summarize_events(events, excluded_month=NOV_2024)
    formation_concentration = concentration(events, "formation")
    oos_concentration = concentration(events, "oos")
    return {
        "research_id": "daily_ma_alignment",
        "scope": "event_audit_not_strategy",
        "parameters": {
            "ema_fast": EMA_FAST,
            "ema_mid": EMA_MID,
            "ema_slow": EMA_SLOW,
            "round_trip_cost": ROUND_TRIP_COST,
            "entry": "next daily open after completed EMA20 > EMA50 > EMA200 alignment first appears",
            "exit": "next daily open after completed EMA20 <= EMA50",
            "overlap_rule": "one open event per symbol; signals during an open event are skipped",
            "november_2024_check": "formation result is also reported excluding 2024-11",
        },
        "formation_period": f"{formation_start} to {formation_end}",
        "oos_period": f"2025-01-01 to {oos_end}",
        "bases": bases,
        "data_sources": data_sources,
        "skipped_symbols": skipped,
        "summary": summary,
        "summary_excluding_2024_11": without_nov_2024,
        "formation_concentration": formation_concentration,
        "oos_concentration": oos_concentration,
        "formation_verdict": verdict(summary, without_nov_2024, formation_concentration, oos_concentration),
        "events": [asdict(event) for event in events],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit daily MA alignment trend events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--bases", nargs="+", default=["BTC", "ETH", "SOL"])
    parser.add_argument("--formation-start", default="2024-01-01")
    parser.add_argument("--formation-end", default="2024-12-31")
    parser.add_argument("--oos-end", default="2025-07-10")
    parser.add_argument("--out", type=Path, default=Path("reports/daily_ma_alignment_audit.json"))
    args = parser.parse_args(argv)
    report = run_audit(args.data, args.bases, args.formation_start, args.formation_end, args.oos_end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
