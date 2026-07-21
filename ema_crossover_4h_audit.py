"""4h EMA crossover trend event audit.

This is research infrastructure, not a runnable strategy.

Frozen rule:
  - resample 15m OHLCV to completed 4h bars
  - EMA20 crossing above EMA50 creates a long signal
  - EMA20 crossing below EMA50 creates a short signal
  - enter on the next 15m open after the completed 4h signal
  - exit on opposite completed 4h cross or max 5-day hold
  - 0.16% round-trip cost
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
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
EMA_FAST = 20
EMA_SLOW = 50
HOLD_BARS = 96 * 5
ROUND_TRIP_COST = 0.0016
EXCLUDED_STRESS_MONTH = "2024-11"


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
class EmaSignal:
    symbol: str
    signal_ts: int
    timestamp_utc: str
    direction: str
    fast_ema: float
    slow_ema: float
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


def resample_4h(bars: list[PriceBar]) -> list[PriceBar]:
    buckets: dict[int, list[PriceBar]] = {}
    for bar in bars:
        bucket_ts = (bar.ts // FOUR_HOURS_MS) * FOUR_HOURS_MS
        buckets.setdefault(bucket_ts, []).append(bar)

    out: list[PriceBar] = []
    for bucket_ts in sorted(buckets):
        group = sorted(buckets[bucket_ts], key=lambda item: item.ts)
        out.append(
            PriceBar(
                ts=bucket_ts,
                timestamp_utc=format_utc(bucket_ts),
                open=group[0].open,
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=group[-1].close,
                volume=sum(item.volume for item in group),
            )
        )
    return out


def ema_values(bars: list[PriceBar], period: int) -> list[float | None]:
    if not bars:
        return []
    alpha = 2.0 / (period + 1.0)
    values: list[float | None] = []
    ema: float | None = None
    for index, bar in enumerate(bars):
        if index + 1 < period:
            values.append(None)
            continue
        if index + 1 == period:
            ema = sum(item.close for item in bars[:period]) / period
        else:
            assert ema is not None
            ema = bar.close * alpha + ema * (1.0 - alpha)
        values.append(ema)
    return values


def split_for_signal(signal_ts: int, formation_start_ts: int, formation_end_ts: int, oos_end_ts: int) -> str | None:
    if formation_start_ts <= signal_ts <= formation_end_ts:
        return "formation"
    if formation_end_ts < signal_ts <= oos_end_ts:
        return "oos"
    return None


def generate_signals(
    symbol: str,
    bars_4h: list[PriceBar],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[EmaSignal]:
    fast = ema_values(bars_4h, EMA_FAST)
    slow = ema_values(bars_4h, EMA_SLOW)
    signals: list[EmaSignal] = []
    for index in range(1, len(bars_4h)):
        if fast[index] is None or slow[index] is None or fast[index - 1] is None or slow[index - 1] is None:
            continue
        signal_ts = bars_4h[index].ts + FOUR_HOURS_MS
        split = split_for_signal(signal_ts, formation_start_ts, formation_end_ts, oos_end_ts)
        if split is None:
            continue
        previous_fast = float(fast[index - 1])
        previous_slow = float(slow[index - 1])
        current_fast = float(fast[index])
        current_slow = float(slow[index])
        if previous_fast <= previous_slow and current_fast > current_slow:
            direction = "long"
        elif previous_fast >= previous_slow and current_fast < current_slow:
            direction = "short"
        else:
            continue
        signals.append(
            EmaSignal(
                symbol=symbol,
                signal_ts=signal_ts,
                timestamp_utc=format_utc(signal_ts),
                direction=direction,
                fast_ema=round(current_fast, 10),
                slow_ema=round(current_slow, 10),
                split=split,
            )
        )
    return signals


def first_bar_after(bars: list[PriceBar], ts: int, start_index: int = 0) -> int | None:
    for index in range(start_index, len(bars)):
        if bars[index].ts > ts:
            return index
    return None


def simulate_trade(signal: EmaSignal, bars_15m: list[PriceBar], entry_index: int, next_signal: EmaSignal | None) -> TradeEvent | None:
    if entry_index >= len(bars_15m):
        return None
    entry = bars_15m[entry_index]
    if entry.open <= 0:
        return None
    final_index = min(entry_index + HOLD_BARS, len(bars_15m) - 1)
    exit_reason = "time"
    if next_signal is not None and next_signal.direction != signal.direction:
        cross_exit_index = first_bar_after(bars_15m, next_signal.signal_ts, entry_index)
        if cross_exit_index is not None and cross_exit_index <= final_index:
            final_index = cross_exit_index
            exit_reason = "opposite_cross"
    if final_index <= entry_index:
        return None

    exit_bar = bars_15m[final_index]
    exit_price = exit_bar.open if exit_reason == "opposite_cross" else exit_bar.close
    gross = exit_price / entry.open - 1.0 if signal.direction == "long" else entry.open / exit_price - 1.0
    net = gross - ROUND_TRIP_COST
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
        gross_return_pct=round(gross * 100.0, 6),
        net_return_pct=round(net * 100.0, 6),
        hold_bars=final_index - entry_index,
    )


def audit_symbol(
    symbol: str,
    bars_15m: list[PriceBar],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[TradeEvent]:
    signals = generate_signals(symbol, resample_4h(bars_15m), formation_start_ts, formation_end_ts, oos_end_ts)
    events: list[TradeEvent] = []
    next_available_ts = 0
    start_index = 0
    for index, signal in enumerate(signals):
        if signal.signal_ts < next_available_ts:
            continue
        entry_index = first_bar_after(bars_15m, signal.signal_ts, start_index)
        if entry_index is None:
            continue
        future_signals = [item for item in signals[index + 1:] if item.direction != signal.direction]
        trade = simulate_trade(signal, bars_15m, entry_index, future_signals[0] if future_signals else None)
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
        "net_sum_pct": round(sum(values), 6),
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


def month_excluded_summary(events: list[TradeEvent], split: str, excluded_month: str = EXCLUDED_STRESS_MONTH) -> dict[str, Any]:
    kept = [event for event in events if event.split == split and event.signal_timestamp_utc[:7] != excluded_month]
    excluded = [event for event in events if event.split == split and event.signal_timestamp_utc[:7] == excluded_month]
    return {
        "excluded_month": excluded_month,
        "excluded_events": len(excluded),
        "kept_events": len(kept),
        "kept_summary": summarize([event.net_return_pct for event in kept]),
        "excluded_summary": summarize([event.net_return_pct for event in excluded]),
    }


def concentration(events: list[TradeEvent], split: str) -> dict[str, Any]:
    split_events = [event for event in events if event.split == split]
    months = Counter(event.signal_timestamp_utc[:7] for event in split_events)
    symbols = Counter(event.symbol for event in split_events)
    positive_by_month: dict[str, float] = {}
    for event in split_events:
        if event.net_return_pct > 0:
            month = event.signal_timestamp_utc[:7]
            positive_by_month[month] = positive_by_month.get(month, 0.0) + event.net_return_pct
    total_positive = sum(positive_by_month.values())
    top_positive = max(positive_by_month.values()) if positive_by_month else 0.0
    top_month = max(months.values()) if months else 0
    top_symbol = max(symbols.values()) if symbols else 0
    return {
        "events": len(split_events),
        "top_month_event_share": round(top_month / len(split_events), 6) if split_events else 0.0,
        "top_symbol_event_share": round(top_symbol / len(split_events), 6) if split_events else 0.0,
        "top_month_positive_contribution_share": round(top_positive / total_positive, 6) if total_positive > 0 else 0.0,
        "events_by_month": dict(sorted(months.items())),
        "events_by_symbol": dict(sorted(symbols.items())),
        "positive_by_month": {key: round(value, 6) for key, value in sorted(positive_by_month.items())},
    }


def formation_verdict(summary: dict[str, Any], formation_concentration: dict[str, Any], ex_2024_11: dict[str, Any]) -> dict[str, Any]:
    stats = summary["formation"]["all"]
    ex_stats = ex_2024_11["kept_summary"]
    reasons: list[str] = []
    if int(stats["observations"]) < 50:
        reasons.append(f"formation events {stats['observations']} < 50")
    if float(stats["mean_pct"]) <= 0:
        reasons.append(f"formation net mean {stats['mean_pct']:+.6f}% <= 0")
    if float(stats["win_rate"]) < 0.45:
        reasons.append(f"formation win rate {stats['win_rate']:.2%} < 45%")
    if float(stats["profit_factor"]) < 1.1:
        reasons.append(f"formation profit factor {stats['profit_factor']:.6f} < 1.1")
    if float(ex_stats["mean_pct"]) <= 0:
        reasons.append(f"formation ex-2024-11 net mean {ex_stats['mean_pct']:+.6f}% <= 0")
    if float(ex_stats["win_rate"]) < 0.45:
        reasons.append(f"formation ex-2024-11 win rate {ex_stats['win_rate']:.2%} < 45%")
    if float(formation_concentration["top_symbol_event_share"]) > 0.30:
        reasons.append(f"top symbol event concentration {formation_concentration['top_symbol_event_share']:.2%} > 30%")
    if float(formation_concentration["top_month_event_share"]) > 0.25:
        reasons.append(f"top month event concentration {formation_concentration['top_month_event_share']:.2%} > 25%")
    return {
        "status": "passed_formation_screen" if not reasons else "rejected",
        "eligible_for_strategy": False,
        "eligible_as_combo_directional_feature": not reasons,
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
        if len(bars) < 16 * (EMA_SLOW + 10):
            skipped[base] = "insufficient_15m_history"
            continue
        symbol = f"{base}-USDT-SWAP"
        events.extend(audit_symbol(symbol, bars, formation_start_ts, formation_end_ts, oos_end_ts))

    summary = summarize_events(events)
    formation_concentration = concentration(events, "formation")
    oos_concentration = concentration(events, "oos")
    ex_2024_11 = month_excluded_summary(events, "formation")
    return {
        "research_id": "4h_ema_crossover",
        "scope": "event_audit_not_strategy",
        "parameters": {
            "fast_ema_4h": EMA_FAST,
            "slow_ema_4h": EMA_SLOW,
            "hold_bars_15m": HOLD_BARS,
            "max_hold_days": 5,
            "round_trip_cost": ROUND_TRIP_COST,
            "entry": "next 15m open after completed 4h EMA cross",
            "exit": "opposite completed 4h EMA cross or 5-day time exit",
            "overlap_rule": "one open event per symbol; signals during an open event are skipped",
        },
        "formation_period": f"{formation_start} to {formation_end}",
        "oos_period": f"2025-01-01 to {oos_end}",
        "n_symbols": len(bases),
        "skipped_symbols": skipped,
        "summary": summary,
        "formation_excluding_2024_11": ex_2024_11,
        "formation_concentration": formation_concentration,
        "oos_concentration": oos_concentration,
        "formation_verdict": formation_verdict(summary, formation_concentration, ex_2024_11),
        "events": [asdict(event) for event in events],
        "event_preview": [asdict(event) for event in events[:25]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit 4h EMA crossover events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--bases", nargs="+")
    parser.add_argument("--formation-start", default="2024-01-01")
    parser.add_argument("--formation-end", default="2024-12-31")
    parser.add_argument("--oos-end", default="2025-07-10")
    parser.add_argument("--out", type=Path, default=Path("reports/ema_crossover_4h_audit.json"))
    args = parser.parse_args(argv)
    bases = args.bases or discover_bases(args.data)
    report = run_audit(args.data, bases, args.formation_start, args.formation_end, args.oos_end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
