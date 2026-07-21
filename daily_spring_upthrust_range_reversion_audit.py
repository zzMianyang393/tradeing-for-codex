"""Frozen audit for daily range-regime spring/upthrust reversions."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from market import Bar, load_quantify_15m_csv, resample_minutes
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from regime_component_walk_forward_audit import DAY_MS, parse_day, trade_event, wilder_atr
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry


RULE_ID = "daily_spring_upthrust_range_reversion_v1"
CHANNEL_DAYS = 20
LONG_CLOSE_LOCATION_MIN = 0.60
SHORT_CLOSE_LOCATION_MAX = 0.40
MAX_HORIZON_MS = 5 * DAY_MS
OOS_END = parse_day("2025-07-10", end=True)


def split(ts: int) -> str | None:
    if parse_day("2024-01-01") <= ts <= parse_day("2024-12-31", end=True):
        return "formation"
    if parse_day("2025-01-01") <= ts <= OOS_END:
        return "oos"
    return None


def signal_direction(bar: Bar, prior_high: float, prior_low: float) -> str | None:
    """Classify a completed false channel break using only the current bar."""
    daily_range = bar.high - bar.low
    if daily_range <= 0:
        return None
    close_location = (bar.close - bar.low) / daily_range
    if bar.low < prior_low and bar.close > prior_low and close_location >= LONG_CLOSE_LOCATION_MIN:
        return "long"
    if bar.high > prior_high and bar.close < prior_high and close_location <= SHORT_CLOSE_LOCATION_MAX:
        return "short"
    return None


def events_for_symbol(symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels, atr = label_completed_4h_bars(bars), wilder_atr(daily, 14)
    events: list[dict[str, Any]] = []
    next_allowed = 0
    for index in range(CHANNEL_DAYS, len(daily) - 6):
        signal_ts = daily[index].ts + DAY_MS
        prior_window = daily[index - CHANNEL_DAYS:index]
        prior_high = max(bar.high for bar in prior_window)
        prior_low = min(bar.low for bar in prior_window)
        direction = signal_direction(daily[index], prior_high, prior_low)
        if (
            direction is None
            or signal_ts < next_allowed
            or split(signal_ts) is None
            or atr[index - 1] is None
            or regime_at_entry(labels, signal_ts) != "震荡"
        ):
            continue
        exit_ts = next(
            (
                daily[j].ts + DAY_MS
                for j in range(index + 1, min(index + 6, len(daily)))
                if (direction == "long" and daily[j].close >= prior_high)
                or (direction == "short" and daily[j].close <= prior_low)
            ),
            None,
        )
        event = trade_event(
            symbol, RULE_ID, direction, signal_ts + FOUR_HOURS_MS, bars, float(atr[index - 1]),
            exit_ts, MAX_HORIZON_MS, OOS_END, "震荡",
        )
        if event is not None:
            event["split"] = split(signal_ts)
            event["channel_high"] = prior_high
            event["channel_low"] = prior_low
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
        "events": len(events),
        "net_sum_pct": round(sum(values), 6),
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
    events = [
        event
        for symbol in symbols
        for event in events_for_symbol(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"))
    ]
    events.sort(key=lambda event: (event["signal_ts"], event["symbol"], event["direction"]))
    formation = summary([event for event in events if event["split"] == "formation"])
    oos = summary([event for event in events if event["split"] == "oos"])
    status, reasons = verdict(formation, oos)
    return {
        "report_type": "daily_spring_upthrust_range_reversion_audit",
        "rule_id": RULE_ID,
        "parameters": {
            "channel_days": CHANNEL_DAYS,
            "long_close_location_min": LONG_CLOSE_LOCATION_MIN,
            "short_close_location_max": SHORT_CLOSE_LOCATION_MAX,
            "entry_delay_hours": 4,
            "stop_atr_multiple": 2.0,
            "max_horizon_days": 5,
            "friction_pct": 0.16,
        },
        "formation": formation,
        "oos": oos,
        "events": events,
        "status": status,
        "reasons": reasons,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_spring_upthrust_range_reversion_audit.json"))
    args = parser.parse_args()
    report = build(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['events']}; oos={report['oos']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
