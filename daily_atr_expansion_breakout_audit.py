"""Frozen audit for daily ATR-confirmed channel breakouts in trend regimes."""
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

RULE_ID = "daily_atr_expansion_breakout_v1"
CHANNEL_DAYS = 20
RANGE_ATR_MULTIPLE = 1.5
OOS_END = parse_day("2025-07-10", end=True)


def split(ts: int) -> str | None:
    if parse_day("2024-01-01") <= ts <= parse_day("2024-12-31", end=True):
        return "formation"
    if parse_day("2025-01-01") <= ts <= OOS_END:
        return "oos"
    return None


def breakout_direction(daily: list[Bar], index: int, atr_value: float | None) -> str | None:
    if index < CHANNEL_DAYS or atr_value is None:
        return None
    prior = daily[index - CHANNEL_DAYS:index]
    if daily[index].high - daily[index].low < RANGE_ATR_MULTIPLE * atr_value:
        return None
    if daily[index].close > max(bar.high for bar in prior):
        return "long"
    if daily[index].close < min(bar.low for bar in prior):
        return "short"
    return None


def events_for_symbol(symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels, atr = label_completed_4h_bars(bars), wilder_atr(daily, 14)
    events: list[dict[str, Any]] = []
    next_allowed = 0
    for index in range(CHANNEL_DAYS, len(daily) - 11):
        signal_ts = daily[index].ts + DAY_MS
        direction = breakout_direction(daily, index, atr[index - 1])
        regime = regime_at_entry(labels, signal_ts)
        if direction is None or signal_ts < next_allowed or split(signal_ts) is None:
            continue
        if (direction == "long" and regime != "趋势上行") or (direction == "short" and regime != "趋势下行"):
            continue
        event = trade_event(symbol, RULE_ID, direction, signal_ts + FOUR_HOURS_MS, bars, float(atr[index - 1]), None, 10 * DAY_MS, OOS_END, regime)
        if event is not None:
            event["split"] = split(signal_ts)
            event["trigger_metrics"] = {"channel_days": CHANNEL_DAYS, "range_atr_multiple": RANGE_ATR_MULTIPLE}
            events.append(event)
            next_allowed = event["exit_ts"] + 900_000
    return events


def summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(event["net_return_pct"]) for event in events]
    by_month: dict[str, float] = defaultdict(float)
    for event in events:
        if event["net_return_pct"] > 0:
            by_month[datetime.fromtimestamp(event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")] += float(event["net_return_pct"])
    positive = sum(by_month.values())
    return {"events": len(events), "net_sum_pct": round(sum(values), 6), "mean_pct": round(mean(values), 6) if values else 0.0,
            "win_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
            "positive_return_month_concentration": round(max(by_month.values()) / positive, 6) if positive else 0.0}


def verdict(formation: dict[str, Any], oos: dict[str, Any]) -> tuple[str, list[str]]:
    reasons, insufficient = [], False
    for name, stats in (("formation", formation), ("oos", oos)):
        if stats["events"] < 15:
            reasons.append(f"{name} events {stats['events']} < 15")
            insufficient = True
        if stats["mean_pct"] <= 0:
            reasons.append(f"{name} mean <= 0")
        if stats["positive_return_month_concentration"] > 0.25:
            reasons.append(f"{name} month concentration {stats['positive_return_month_concentration']:.1%} > 25%")
    return ("insufficient_evidence" if insufficient else "historical_rejected" if reasons else "historical_research_candidate"), reasons


def build(data_dir: Path, symbols: list[str]) -> dict[str, Any]:
    events = [event for symbol in symbols for event in events_for_symbol(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"))]
    events.sort(key=lambda event: (event["signal_ts"], event["symbol"], event["direction"]))
    formation, oos = (summary([event for event in events if event["split"] == name]) for name in ("formation", "oos"))
    status, reasons = verdict(formation, oos)
    return {"report_type": "daily_atr_expansion_breakout_audit", "rule_id": RULE_ID,
            "parameters": {"channel_days": CHANNEL_DAYS, "range_atr_multiple": RANGE_ATR_MULTIPLE, "entry_delay_hours": 4, "stop_atr_multiple": 2.0, "max_horizon_days": 10, "friction_pct": 0.16},
            "formation": formation, "oos": oos, "events": events, "status": status, "reasons": reasons,
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_atr_expansion_breakout_audit.json"))
    args = parser.parse_args()
    report = build(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['events']}; oos={report['oos']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
