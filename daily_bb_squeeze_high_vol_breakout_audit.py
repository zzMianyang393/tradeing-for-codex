"""Frozen audit for daily Bollinger squeeze breakouts in high-volatility transitions."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from market import Bar, load_quantify_15m_csv, resample_minutes
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from regime_component_walk_forward_audit import DAY_MS, parse_day, trade_event, wilder_atr
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry


RULE_ID = "daily_bb_squeeze_high_vol_breakout_v1"
BB_PERIOD = 20
BB_STDDEV = 2.0
WIDTH_HISTORY_DAYS = 120
WIDTH_PERCENTILE = 0.20
HIGH_VOL_TRANSITION = "高波动转换"
MAX_HORIZON_MS = 10 * DAY_MS
OOS_END = parse_day("2025-07-10", end=True)


def split(ts: int) -> str | None:
    if parse_day("2024-01-01") <= ts <= parse_day("2024-12-31", end=True):
        return "formation"
    if parse_day("2025-01-01") <= ts <= OOS_END:
        return "oos"
    return None


def bollinger_widths(bars: list[Bar]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    middles: list[float | None] = [None] * len(bars)
    uppers: list[float | None] = [None] * len(bars)
    lowers: list[float | None] = [None] * len(bars)
    for index in range(BB_PERIOD - 1, len(bars)):
        closes = [bar.close for bar in bars[index - BB_PERIOD + 1:index + 1]]
        middle = mean(closes)
        deviation = pstdev(closes)
        middles[index] = middle
        uppers[index] = middle + BB_STDDEV * deviation
        lowers[index] = middle - BB_STDDEV * deviation
    return middles, uppers, lowers


def width(middle: float | None, upper: float | None, lower: float | None) -> float | None:
    if middle is None or upper is None or lower is None or middle <= 0:
        return None
    return (upper - lower) / middle


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def events_for_symbol(symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels, atr = label_completed_4h_bars(bars), wilder_atr(daily, 14)
    middles, uppers, lowers = bollinger_widths(daily)
    widths = [width(middle, upper, lower) for middle, upper, lower in zip(middles, uppers, lowers)]
    events: list[dict[str, Any]] = []
    next_allowed = 0
    start = BB_PERIOD - 1 + WIDTH_HISTORY_DAYS
    for index in range(max(start, 14), len(daily) - 11):
        signal_ts = daily[index].ts + DAY_MS
        prior_widths = [value for value in widths[index - WIDTH_HISTORY_DAYS:index] if value is not None]
        current_width = widths[index]
        upper, lower = uppers[index], lowers[index]
        direction = "long" if upper is not None and daily[index].close > upper else "short" if lower is not None and daily[index].close < lower else None
        if (
            direction is None
            or signal_ts < next_allowed
            or split(signal_ts) is None
            or atr[index - 1] is None
            or current_width is None
            or len(prior_widths) < WIDTH_HISTORY_DAYS
            or current_width > percentile(prior_widths, WIDTH_PERCENTILE)
            or regime_at_entry(labels, signal_ts) != HIGH_VOL_TRANSITION
        ):
            continue
        exit_ts = next(
            (
                daily[j].ts + DAY_MS
                for j in range(index + 1, min(index + 11, len(daily)))
                if middles[j] is not None
                and ((direction == "long" and daily[j].close < middles[j]) or (direction == "short" and daily[j].close > middles[j]))
            ),
            None,
        )
        event = trade_event(symbol, RULE_ID, direction, signal_ts + FOUR_HOURS_MS, bars, float(atr[index - 1]), exit_ts, MAX_HORIZON_MS, OOS_END, HIGH_VOL_TRANSITION)
        if event is not None:
            event["split"] = split(signal_ts)
            event["bb_width"] = round(current_width, 8)
            events.append(event)
            next_allowed = event["exit_ts"] + 900_000
    return events


def summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(event["net_return_pct"]) for event in events]
    positive_by_month: dict[str, float] = defaultdict(float)
    for event in events:
        if event["net_return_pct"] > 0:
            month = datetime.fromtimestamp(event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")
            positive_by_month[month] += float(event["net_return_pct"])
    positive_total = sum(positive_by_month.values())
    return {
        "events": len(events), "net_sum_pct": round(sum(values), 6),
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "win_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
        "positive_return_month_concentration": round(max(positive_by_month.values()) / positive_total, 6) if positive_total else 0.0,
    }


def verdict(formation: dict[str, Any], oos: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    insufficient = False
    for name, stats in (("formation", formation), ("oos", oos)):
        if stats["events"] < 15:
            reasons.append(f"{name} events {stats['events']} < 15")
            insufficient = True
        if stats["mean_pct"] <= 0:
            reasons.append(f"{name} mean <= 0")
        if stats["positive_return_month_concentration"] > 0.25:
            reasons.append(f"{name} month concentration {stats['positive_return_month_concentration']:.1%} > 25%")
    if insufficient:
        return "insufficient_evidence", reasons
    return ("historical_rejected" if reasons else "historical_research_candidate"), reasons


def build(data_dir: Path, symbols: list[str]) -> dict[str, Any]:
    events = [event for symbol in symbols for event in events_for_symbol(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"))]
    events.sort(key=lambda event: (event["signal_ts"], event["symbol"], event["direction"]))
    formation = summary([event for event in events if event["split"] == "formation"])
    oos = summary([event for event in events if event["split"] == "oos"])
    status, reasons = verdict(formation, oos)
    return {
        "report_type": "daily_bb_squeeze_high_vol_breakout_audit", "rule_id": RULE_ID,
        "parameters": {"bb_period": BB_PERIOD, "bb_stddev": BB_STDDEV, "width_history_days": WIDTH_HISTORY_DAYS,
                       "width_percentile": WIDTH_PERCENTILE, "entry_delay_hours": 4, "stop_atr_multiple": 2.0,
                       "max_horizon_days": 10, "friction_pct": 0.16},
        "formation": formation, "oos": oos, "events": events, "status": status, "reasons": reasons,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_bb_squeeze_high_vol_breakout_audit.json"))
    args = parser.parse_args()
    report = build(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['events']}; oos={report['oos']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
