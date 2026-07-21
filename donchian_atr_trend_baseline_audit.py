"""Donchian + ATR trend baseline event audit.

This is research infrastructure, not a runnable strategy.  It implements the
pre-registered rule from docs/donchian_atr_trend_baseline_research_card.md:

  - completed daily close breaks the prior 20-day Donchian channel
  - enter on the next 15m open after the daily candle is complete
  - fixed stop at 2 * daily ATR(14) from entry
  - maximum hold 10 days (960 * 15m bars)
  - 0.16% round-trip cost

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


FIFTEEN_MINUTES_MS = 15 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
DONCHIAN_DAYS = 20
ATR_DAYS = 14
ATR_STOP_MULTIPLE = 2.0
HOLD_BARS = 96 * 10
ROUND_TRIP_COST = 0.0016


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
class DailySignal:
    symbol: str
    signal_ts: int
    timestamp_utc: str
    direction: str
    close: float
    donchian_high: float
    donchian_low: float
    atr: float
    split: str


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
    stop_price: float
    gross_return_pct: float
    net_return_pct: float
    hold_bars: int


def parse_timestamp_ms(value: str) -> int:
    stripped = value.strip()
    if stripped.isdigit():
        raw = int(stripped)
        if raw < 10_000_000_000:
            return raw * 1000
        return raw
    return int(datetime.strptime(stripped, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load_ohlcv_15m(path: Path) -> list[PriceBar]:
    bars: list[PriceBar] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                raw_ts = row.get("timestamp_ms") or row["timestamp"]
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


def discover_bases(data_dir: Path) -> list[str]:
    return sorted(path.name.removesuffix("_15m.csv") for path in data_dir.glob("*_15m.csv"))


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


def true_ranges(daily: list[PriceBar]) -> list[float]:
    ranges: list[float] = []
    previous_close = daily[0].close if daily else 0.0
    for index, bar in enumerate(daily):
        if index == 0:
            ranges.append(bar.high - bar.low)
        else:
            ranges.append(max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close)))
        previous_close = bar.close
    return ranges


def rolling_atr(daily: list[PriceBar], period: int = ATR_DAYS) -> list[float | None]:
    ranges = true_ranges(daily)
    values: list[float | None] = []
    for index in range(len(ranges)):
        if index + 1 < period:
            values.append(None)
        else:
            window = ranges[index + 1 - period:index + 1]
            values.append(sum(window) / period)
    return values


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
) -> list[DailySignal]:
    atr_values = rolling_atr(daily)
    signals: list[DailySignal] = []
    for index, bar in enumerate(daily):
        if index < DONCHIAN_DAYS:
            continue
        atr = atr_values[index]
        if atr is None or atr <= 0:
            continue
        signal_ts = bar.ts + DAY_MS
        split = split_for_signal(signal_ts, formation_start_ts, formation_end_ts, oos_end_ts)
        if split is None:
            continue
        prior = daily[index - DONCHIAN_DAYS:index]
        channel_high = max(item.high for item in prior)
        channel_low = min(item.low for item in prior)
        if bar.close > channel_high:
            direction = "long"
        elif bar.close < channel_low:
            direction = "short"
        else:
            continue
        signals.append(
            DailySignal(
                symbol=symbol,
                signal_ts=signal_ts,
                timestamp_utc=format_utc(signal_ts),
                direction=direction,
                close=bar.close,
                donchian_high=channel_high,
                donchian_low=channel_low,
                atr=atr,
                split=split,
            )
        )
    return signals


def first_bar_after(bars: list[PriceBar], ts: int, start_index: int = 0) -> int | None:
    for index in range(start_index, len(bars)):
        if bars[index].ts > ts:
            return index
    return None


def simulate_trade(signal: DailySignal, bars_15m: list[PriceBar], entry_index: int) -> TradeEvent | None:
    if entry_index >= len(bars_15m):
        return None
    entry = bars_15m[entry_index]
    if entry.open <= 0:
        return None
    is_long = signal.direction == "long"
    stop = entry.open - ATR_STOP_MULTIPLE * signal.atr if is_long else entry.open + ATR_STOP_MULTIPLE * signal.atr
    final_index = min(entry_index + HOLD_BARS, len(bars_15m) - 1)
    if final_index <= entry_index:
        return None

    exit_index = final_index
    exit_price = bars_15m[final_index].close
    exit_reason = "time"
    for index in range(entry_index, final_index + 1):
        bar = bars_15m[index]
        if is_long and bar.low <= stop:
            exit_index = index
            exit_price = stop
            exit_reason = "stop"
            break
        if not is_long and bar.high >= stop:
            exit_index = index
            exit_price = stop
            exit_reason = "stop"
            break

    gross = exit_price / entry.open - 1.0 if is_long else entry.open / exit_price - 1.0
    net = gross - ROUND_TRIP_COST
    exit_bar = bars_15m[exit_index]
    return TradeEvent(
        symbol=signal.symbol,
        direction=signal.direction,
        split=signal.split,
        signal_ts=signal.signal_ts,
        signal_timestamp_utc=signal.timestamp_utc,
        entry_ts=entry.ts,
        entry_timestamp_utc=entry.timestamp_utc,
        exit_ts=exit_bar.ts,
        exit_timestamp_utc=exit_bar.timestamp_utc,
        exit_reason=exit_reason,
        entry_price=round(entry.open, 10),
        exit_price=round(exit_price, 10),
        stop_price=round(stop, 10),
        gross_return_pct=round(gross * 100.0, 6),
        net_return_pct=round(net * 100.0, 6),
        hold_bars=exit_index - entry_index,
    )


def audit_symbol(
    symbol: str,
    bars_15m: list[PriceBar],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[TradeEvent]:
    signals = generate_signals(symbol, resample_daily(bars_15m), formation_start_ts, formation_end_ts, oos_end_ts)
    events: list[TradeEvent] = []
    next_available_ts = 0
    start_index = 0
    for signal in signals:
        if signal.signal_ts < next_available_ts:
            continue
        entry_index = first_bar_after(bars_15m, signal.signal_ts, start_index)
        if entry_index is None:
            continue
        trade = simulate_trade(signal, bars_15m, entry_index)
        if trade is None:
            continue
        events.append(trade)
        next_available_ts = trade.exit_ts + FIFTEEN_MINUTES_MS
        start_index = entry_index
    return events


def summarize(values: list[float]) -> dict[str, float | int]:
    positives = [value for value in values if value > 0]
    negatives = [value for value in values if value <= 0]
    gross_profit = sum(positives)
    gross_loss = abs(sum(negatives))
    return {
        "observations": len(values),
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "median_pct": round(median(values), 6) if values else 0.0,
        "win_rate": round(len(positives) / len(values), 6) if values else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "gross_profit_pct": round(gross_profit, 6),
        "gross_loss_pct": round(gross_loss, 6),
    }


def summarize_events(events: list[TradeEvent]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split in ("formation", "oos"):
        split_events = [event for event in events if event.split == split]
        result[split] = {
            "all": summarize([event.net_return_pct for event in split_events]),
            "long": summarize([event.net_return_pct for event in split_events if event.direction == "long"]),
            "short": summarize([event.net_return_pct for event in split_events if event.direction == "short"]),
            "exit_reasons": dict(Counter(event.exit_reason for event in split_events)),
            "direction_counts": dict(Counter(event.direction for event in split_events)),
        }
    return result


def concentration(events: list[TradeEvent], split: str) -> dict[str, Any]:
    split_events = [event for event in events if event.split == split]
    months = Counter(event.signal_timestamp_utc[:7] for event in split_events)
    symbols = Counter(event.symbol for event in split_events)
    top_month = max(months.values()) if months else 0
    top_symbol = max(symbols.values()) if symbols else 0
    return {
        "events": len(split_events),
        "top_month_share": round(top_month / len(split_events), 6) if split_events else 0.0,
        "top_symbol_share": round(top_symbol / len(split_events), 6) if split_events else 0.0,
        "events_by_month": dict(sorted(months.items())),
        "events_by_symbol": dict(sorted(symbols.items())),
    }


def formation_verdict(summary: dict[str, Any], formation_concentration: dict[str, Any]) -> dict[str, Any]:
    stats = summary["formation"]["all"]
    reasons: list[str] = []
    if int(stats["observations"]) < 50:
        reasons.append(f"formation events {stats['observations']} < 50")
    if float(stats["mean_pct"]) <= 0:
        reasons.append(f"formation net mean {stats['mean_pct']:+.6f}% <= 0")
    if float(stats["win_rate"]) < 0.45:
        reasons.append(f"formation win rate {stats['win_rate']:.2%} < 45%")
    if float(stats["profit_factor"]) < 1.2:
        reasons.append(f"formation profit factor {stats['profit_factor']:.6f} < 1.2")
    if float(formation_concentration["top_symbol_share"]) > 0.30:
        reasons.append(f"top symbol concentration {formation_concentration['top_symbol_share']:.2%} > 30%")
    if float(formation_concentration["top_month_share"]) > 0.25:
        reasons.append(f"top month concentration {formation_concentration['top_month_share']:.2%} > 25%")
    return {
        "status": "passed_formation_screen" if not reasons else "rejected",
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
    formation_start_ts = parse_timestamp_ms(f"{formation_start} 00:00:00")
    formation_end_ts = parse_timestamp_ms(f"{formation_end} 23:59:59")
    oos_end_ts = parse_timestamp_ms(f"{oos_end} 23:59:59")
    events: list[TradeEvent] = []
    skipped: dict[str, str] = {}
    for base in bases:
        path = data_dir / f"{base}_15m.csv"
        if not path.exists():
            skipped[base] = "missing_15m_csv"
            continue
        bars = load_ohlcv_15m(path)
        if len(bars) < 96 * (DONCHIAN_DAYS + ATR_DAYS + 10):
            skipped[base] = "insufficient_15m_history"
            continue
        symbol = f"{base}-USDT-SWAP"
        symbol_events = audit_symbol(symbol, bars, formation_start_ts, formation_end_ts, oos_end_ts)
        events.extend(symbol_events)

    summary = summarize_events(events)
    formation_concentration = concentration(events, "formation")
    oos_concentration = concentration(events, "oos")
    verdict = formation_verdict(summary, formation_concentration)
    return {
        "research_id": "donchian_atr_trend_baseline",
        "scope": "event_audit_not_strategy",
        "parameters": {
            "donchian_days": DONCHIAN_DAYS,
            "atr_days": ATR_DAYS,
            "atr_stop_multiple": ATR_STOP_MULTIPLE,
            "hold_bars_15m": HOLD_BARS,
            "round_trip_cost": ROUND_TRIP_COST,
            "entry": "next 15m open after completed daily breakout confirmation",
            "exit": "fixed 2xATR stop or 10-day time exit; no trailing stop",
            "overlap_rule": "one open event per symbol; signals during an open event are skipped",
        },
        "formation_period": f"{formation_start} to {formation_end}",
        "oos_period": f"2025-01-01 to {oos_end}",
        "n_symbols": len(bases),
        "skipped_symbols": skipped,
        "summary": summary,
        "formation_concentration": formation_concentration,
        "oos_concentration": oos_concentration,
        "formation_verdict": verdict,
        "events": [asdict(event) for event in events],
        "event_preview": [asdict(event) for event in events[:25]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Donchian + ATR trend baseline events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--bases", nargs="+")
    parser.add_argument("--formation-start", default="2024-01-01")
    parser.add_argument("--formation-end", default="2024-12-31")
    parser.add_argument("--oos-end", default="2025-07-10")
    parser.add_argument("--out", type=Path, default=Path("reports/donchian_atr_trend_baseline_audit.json"))
    args = parser.parse_args(argv)
    bases = args.bases or discover_bases(args.data)
    report = run_audit(args.data, bases, args.formation_start, args.formation_end, args.oos_end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
