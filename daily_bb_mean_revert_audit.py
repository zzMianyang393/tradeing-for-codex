"""Daily Bollinger mean-reversion audit.

This is research infrastructure, not a runnable strategy. It implements one
pre-registered low-turnover representative rule:

  - use completed daily candles
  - go long when daily close < BB(20, 2.0) lower band
  - enter on the next daily open
  - exit on the next daily open after daily close >= BB middle band
  - if no middle-band recovery occurs, exit after 10 daily bars
  - one position per symbol; signals while a position is open are skipped
  - 0.16% single-market round-trip cost

No parameter scan is performed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


DAY_MS = 24 * 60 * 60 * 1000
BB_PERIOD = 20
BB_STD_MULTIPLE = 2.0
MAX_HOLD_DAYS = 10
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
class BollingerSignal:
    symbol: str
    signal_ts: int
    signal_timestamp_utc: str
    split: str
    close: float
    bb_mid: float
    bb_lower: float


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


def rolling_bollinger(
    daily: list[PriceBar],
    period: int = BB_PERIOD,
    std_multiple: float = BB_STD_MULTIPLE,
) -> list[tuple[float, float] | None]:
    closes = [bar.close for bar in daily]
    values: list[tuple[float, float] | None] = []
    for index in range(len(closes)):
        if index + 1 < period:
            values.append(None)
            continue
        window = closes[index + 1 - period:index + 1]
        mid = sum(window) / period
        variance = sum((value - mid) ** 2 for value in window) / period
        lower = mid - std_multiple * math.sqrt(variance)
        values.append((mid, lower))
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
) -> list[BollingerSignal]:
    bb_values = rolling_bollinger(daily)
    signals: list[BollingerSignal] = []
    for index in range(len(daily) - 1):
        bb = bb_values[index]
        if bb is None:
            continue
        bb_mid, bb_lower = bb
        if daily[index].close >= bb_lower:
            continue
        signal_ts = daily[index].ts + DAY_MS
        split = split_for_signal(signal_ts, formation_start_ts, formation_end_ts, oos_end_ts)
        if split is None:
            continue
        signals.append(
            BollingerSignal(
                symbol=symbol,
                signal_ts=signal_ts,
                signal_timestamp_utc=format_utc(signal_ts),
                split=split,
                close=round(daily[index].close, 10),
                bb_mid=round(bb_mid, 10),
                bb_lower=round(bb_lower, 10),
            )
        )
    return signals


def first_bar_at_or_after(daily: list[PriceBar], ts: int, start_index: int = 0) -> int | None:
    for index in range(start_index, len(daily)):
        if daily[index].ts >= ts:
            return index
    return None


def find_exit_index(daily: list[PriceBar], entry_index: int) -> tuple[int | None, str]:
    bb_values = rolling_bollinger(daily)
    final_signal_index = min(entry_index + MAX_HOLD_DAYS - 1, len(daily) - 2)
    if final_signal_index < entry_index:
        return None, "open_position_no_exit"
    for signal_index in range(entry_index, final_signal_index + 1):
        bb = bb_values[signal_index]
        if bb is None:
            continue
        bb_mid, _ = bb
        if daily[signal_index].close >= bb_mid:
            return signal_index + 1, "bb_mid_recovery"
    return final_signal_index + 1, "time"


def simulate_trade(signal: BollingerSignal, daily: list[PriceBar], entry_index: int) -> TradeEvent | None:
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
    return {
        split: summarize(
            [
                event.net_return_pct
                for event in events
                if event.split == split and (excluded_month is None or event.signal_timestamp_utc[:7] != excluded_month)
            ]
        )
        for split in ("formation", "oos")
    }


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
    if float(formation["win_rate"]) < 0.50:
        reasons.append(f"formation win rate {formation['win_rate']:.2%} < 50%")
    if float(formation["profit_factor"]) < 1.2:
        reasons.append(f"formation profit factor {formation['profit_factor']:.6f} < 1.2")
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
    return {
        "status": "rejected" if reasons else "passed_research_screen",
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
        if len(daily) < BB_PERIOD + MAX_HOLD_DAYS + 20:
            skipped[base] = "insufficient_daily_history"
            continue
        events.extend(audit_symbol(f"{base}-USDT-SWAP", daily, formation_start_ts, formation_end_ts, oos_end_ts))

    summary = summarize_events(events)
    without_nov_2024 = summarize_events(events, excluded_month=NOV_2024)
    formation_concentration = concentration(events, "formation")
    oos_concentration = concentration(events, "oos")
    return {
        "research_id": "daily_bb_mean_revert",
        "scope": "event_audit_not_strategy",
        "parameters": {
            "bb_period": BB_PERIOD,
            "bb_std_multiple": BB_STD_MULTIPLE,
            "max_hold_days": MAX_HOLD_DAYS,
            "round_trip_cost": ROUND_TRIP_COST,
            "entry": "next daily open after completed daily close below BB lower band",
            "exit": "next daily open after completed daily close recovers to BB middle band, or 10-day time exit",
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
    parser = argparse.ArgumentParser(description="Audit daily Bollinger mean-reversion events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--bases", nargs="+", default=["BTC", "ETH", "SOL"])
    parser.add_argument("--formation-start", default="2024-01-01")
    parser.add_argument("--formation-end", default="2024-12-31")
    parser.add_argument("--oos-end", default="2025-07-10")
    parser.add_argument("--out", type=Path, default=Path("reports/daily_bb_mean_revert_audit.json"))
    args = parser.parse_args(argv)
    report = run_audit(args.data, args.bases, args.formation_start, args.formation_end, args.oos_end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
