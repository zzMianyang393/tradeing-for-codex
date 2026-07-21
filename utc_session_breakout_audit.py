"""UTC session breakout event audit.

This is research infrastructure, not a runnable strategy.  It implements the
pre-registered rule from docs/utc_session_breakout_research_card.md:

  - build the UTC 00:00-04:00 range from 15m bars
  - after the range completes, wait for a completed 15m close above range high
  - enter long on the next 15m open
  - fixed stop at 2 * ATR(14), fixed target at 3 * ATR(14)
  - maximum hold 20h (80 * 15m bars)
  - 0.16% round-trip cost

No parameter scan is performed.
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
DAY_MS = 24 * 60 * 60 * 1000
RANGE_START_HOUR = 0
RANGE_END_HOUR = 4
RANGE_BARS = 16
ATR_PERIOD = 14
ATR_STOP_MULTIPLE = 2.0
ATR_TARGET_MULTIPLE = 3.0
HOLD_BARS = 80
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
class BreakoutSignal:
    symbol: str
    signal_ts: int
    timestamp_utc: str
    range_start_ts: int
    range_end_ts: int
    range_high: float
    range_low: float
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
    range_high: float
    range_low: float
    atr: float
    entry_price: float
    exit_price: float
    stop_price: float
    take_profit_price: float
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


def day_start(ts: int) -> int:
    return (ts // DAY_MS) * DAY_MS


def true_ranges(bars: list[PriceBar]) -> list[float]:
    ranges: list[float] = []
    previous_close = bars[0].close if bars else 0.0
    for index, bar in enumerate(bars):
        if index == 0:
            ranges.append(bar.high - bar.low)
        else:
            ranges.append(max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close)))
        previous_close = bar.close
    return ranges


def rolling_atr(bars: list[PriceBar], period: int = ATR_PERIOD) -> list[float | None]:
    ranges = true_ranges(bars)
    values: list[float | None] = []
    for index in range(len(ranges)):
        if index + 1 < period:
            values.append(None)
        else:
            values.append(sum(ranges[index + 1 - period:index + 1]) / period)
    return values


def split_for_signal(signal_ts: int, formation_start_ts: int, formation_end_ts: int, oos_end_ts: int) -> str | None:
    if formation_start_ts <= signal_ts <= formation_end_ts:
        return "formation"
    if formation_end_ts < signal_ts <= oos_end_ts:
        return "oos"
    return None


def generate_signals(
    symbol: str,
    bars: list[PriceBar],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[BreakoutSignal]:
    if not bars:
        return []
    atr_values = rolling_atr(bars)
    by_ts = {bar.ts: (index, bar) for index, bar in enumerate(bars)}
    days = sorted({day_start(bar.ts) for bar in bars})
    signals: list[BreakoutSignal] = []
    for day_ts in days:
        range_start = day_ts + RANGE_START_HOUR * 60 * 60 * 1000
        range_end = day_ts + RANGE_END_HOUR * 60 * 60 * 1000
        range_items: list[PriceBar] = []
        missing = False
        for offset in range(RANGE_BARS):
            item = by_ts.get(range_start + offset * FIFTEEN_MINUTES_MS)
            if item is None:
                missing = True
                break
            range_items.append(item[1])
        if missing:
            continue
        range_high = max(bar.high for bar in range_items)
        range_low = min(bar.low for bar in range_items)
        last_range_index = by_ts[range_start + (RANGE_BARS - 1) * FIFTEEN_MINUTES_MS][0]
        atr = atr_values[last_range_index]
        if atr is None or atr <= 0:
            continue
        search_start = last_range_index + 1
        search_end_ts = day_ts + DAY_MS
        for index in range(search_start, len(bars) - 1):
            bar = bars[index]
            if bar.ts < range_end:
                continue
            if bar.ts >= search_end_ts:
                break
            if bar.close > range_high:
                signal_ts = bar.ts + FIFTEEN_MINUTES_MS
                split = split_for_signal(signal_ts, formation_start_ts, formation_end_ts, oos_end_ts)
                if split is None:
                    break
                signals.append(
                    BreakoutSignal(
                        symbol=symbol,
                        signal_ts=signal_ts,
                        timestamp_utc=format_utc(signal_ts),
                        range_start_ts=range_start,
                        range_end_ts=range_end,
                        range_high=range_high,
                        range_low=range_low,
                        atr=atr,
                        split=split,
                    )
                )
                break
    return signals


def first_bar_at_or_after(bars: list[PriceBar], ts: int, start_index: int = 0) -> int | None:
    for index in range(start_index, len(bars)):
        if bars[index].ts >= ts:
            return index
    return None


def simulate_trade(signal: BreakoutSignal, bars: list[PriceBar], entry_index: int) -> TradeEvent | None:
    if entry_index >= len(bars):
        return None
    entry = bars[entry_index]
    if entry.open <= 0:
        return None
    stop = entry.open - ATR_STOP_MULTIPLE * signal.atr
    target = entry.open + ATR_TARGET_MULTIPLE * signal.atr
    final_index = min(entry_index + HOLD_BARS, len(bars) - 1)
    if final_index < entry_index:
        return None

    exit_index = final_index
    exit_price = bars[final_index].close
    exit_reason = "time"
    for index in range(entry_index, final_index + 1):
        bar = bars[index]
        if bar.low <= stop:
            exit_index = index
            exit_price = stop
            exit_reason = "stop"
            break
        if bar.high >= target:
            exit_index = index
            exit_price = target
            exit_reason = "target"
            break

    gross = exit_price / entry.open - 1.0
    net = gross - ROUND_TRIP_COST
    exit_bar = bars[exit_index]
    return TradeEvent(
        symbol=signal.symbol,
        direction="long",
        split=signal.split,
        signal_ts=signal.signal_ts,
        signal_timestamp_utc=signal.timestamp_utc,
        entry_ts=entry.ts,
        entry_timestamp_utc=entry.timestamp_utc,
        exit_ts=exit_bar.ts,
        exit_timestamp_utc=exit_bar.timestamp_utc,
        exit_reason=exit_reason,
        range_high=round(signal.range_high, 10),
        range_low=round(signal.range_low, 10),
        atr=round(signal.atr, 10),
        entry_price=round(entry.open, 10),
        exit_price=round(exit_price, 10),
        stop_price=round(stop, 10),
        take_profit_price=round(target, 10),
        gross_return_pct=round(gross * 100.0, 6),
        net_return_pct=round(net * 100.0, 6),
        hold_bars=exit_index - entry_index,
    )


def audit_symbol(
    symbol: str,
    bars: list[PriceBar],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[TradeEvent]:
    signals = generate_signals(symbol, bars, formation_start_ts, formation_end_ts, oos_end_ts)
    events: list[TradeEvent] = []
    start_index = 0
    for signal in signals:
        entry_index = first_bar_at_or_after(bars, signal.signal_ts, start_index)
        if entry_index is None:
            continue
        trade = simulate_trade(signal, bars, entry_index)
        if trade is None:
            continue
        events.append(trade)
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
            "exit_reasons": dict(Counter(event.exit_reason for event in split_events)),
        }
    return result


def concentration(events: list[TradeEvent], split: str) -> dict[str, Any]:
    split_events = [event for event in events if event.split == split]
    months = Counter(event.signal_timestamp_utc[:7] for event in split_events)
    symbols = Counter(event.symbol for event in split_events)
    profits_by_symbol: dict[str, float] = defaultdict(float)
    for event in split_events:
        if event.net_return_pct > 0:
            profits_by_symbol[event.symbol] += event.net_return_pct
    gross_profit = sum(profits_by_symbol.values())
    top_month = max(months.values()) if months else 0
    top_symbol_events = max(symbols.values()) if symbols else 0
    top_symbol_profit = max(profits_by_symbol.values()) if profits_by_symbol else 0.0
    return {
        "events": len(split_events),
        "top_month_event_share": round(top_month / len(split_events), 6) if split_events else 0.0,
        "top_symbol_event_share": round(top_symbol_events / len(split_events), 6) if split_events else 0.0,
        "top_symbol_profit_share": round(top_symbol_profit / gross_profit, 6) if gross_profit > 0 else 0.0,
        "events_by_month": dict(sorted(months.items())),
        "events_by_symbol": dict(sorted(symbols.items())),
        "positive_profit_by_symbol": {key: round(value, 6) for key, value in sorted(profits_by_symbol.items())},
    }


def formation_verdict(summary: dict[str, Any], formation_concentration: dict[str, Any]) -> dict[str, Any]:
    stats = summary["formation"]["all"]
    reasons: list[str] = []
    if int(stats["observations"]) < 60:
        reasons.append(f"formation events {stats['observations']} < 60")
    if float(stats["mean_pct"]) <= 0:
        reasons.append(f"formation net mean {stats['mean_pct']:+.6f}% <= 0")
    if float(stats["win_rate"]) < 0.45:
        reasons.append(f"formation win rate {stats['win_rate']:.2%} < 45%")
    if float(stats["profit_factor"]) < 1.2:
        reasons.append(f"formation profit factor {stats['profit_factor']:.6f} < 1.2")
    if float(formation_concentration["top_symbol_profit_share"]) > 0.30:
        reasons.append(f"top symbol profit concentration {formation_concentration['top_symbol_profit_share']:.2%} > 30%")
    if float(formation_concentration["top_month_event_share"]) > 0.25:
        reasons.append(f"top month event concentration {formation_concentration['top_month_event_share']:.2%} > 25%")
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
        if len(bars) < 96 * 30:
            skipped[base] = "insufficient_15m_history"
            continue
        events.extend(audit_symbol(f"{base}-USDT-SWAP", bars, formation_start_ts, formation_end_ts, oos_end_ts))

    summary = summarize_events(events)
    formation_concentration = concentration(events, "formation")
    oos_concentration = concentration(events, "oos")
    return {
        "research_id": "utc_session_breakout_family",
        "scope": "event_audit_not_strategy",
        "parameters": {
            "range_window_utc": "00:00-04:00",
            "direction": "long_only",
            "atr_period_15m": ATR_PERIOD,
            "atr_stop_multiple": ATR_STOP_MULTIPLE,
            "atr_target_multiple": ATR_TARGET_MULTIPLE,
            "hold_bars_15m": HOLD_BARS,
            "round_trip_cost": ROUND_TRIP_COST,
            "entry": "next 15m open after completed 15m close above 00:00-04:00 range high",
            "exit": "fixed 2xATR stop, fixed 3xATR target, or 20h time exit",
            "same_bar_path_rule": "stop is checked before target when both occur in the same 15m bar",
            "event_rule": "at most one long breakout event per symbol per UTC day",
        },
        "formation_period": f"{formation_start} to {formation_end}",
        "oos_period": f"2025-01-01 to {oos_end}",
        "n_symbols": len(bases),
        "skipped_symbols": skipped,
        "summary": summary,
        "formation_concentration": formation_concentration,
        "oos_concentration": oos_concentration,
        "formation_verdict": formation_verdict(summary, formation_concentration),
        "event_preview": [asdict(event) for event in events[:25]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit UTC 00:00-04:00 session breakout events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--bases", nargs="+")
    parser.add_argument("--formation-start", default="2024-01-01")
    parser.add_argument("--formation-end", default="2024-12-31")
    parser.add_argument("--oos-end", default="2025-07-10")
    parser.add_argument("--out", type=Path, default=Path("reports/utc_session_breakout_audit.json"))
    args = parser.parse_args(argv)
    bases = args.bases or discover_bases(args.data)
    report = run_audit(args.data, bases, args.formation_start, args.formation_end, args.oos_end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
