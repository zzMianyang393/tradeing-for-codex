"""Frozen audit for daily Williams %R(14) mean reversion in the range regime."""
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

RULE_ID = "daily_williams_r_range_reversion_v1"
RANGE_REGIME = "\u9707\u8361"
LOOKBACK = 14
LOW_THRESHOLD = -90.0
HIGH_THRESHOLD = -10.0
MIDPOINT = -50.0
OOS_END = parse_day("2025-07-10", end=True)


def split(ts: int) -> str | None:
    if parse_day("2024-01-01") <= ts <= parse_day("2024-12-31", end=True):
        return "formation"
    if parse_day("2025-01-01") <= ts <= OOS_END:
        return "oos"
    return None


def williams_r(bars: list[Bar], index: int) -> float | None:
    if index < LOOKBACK - 1:
        return None
    window = bars[index - LOOKBACK + 1:index + 1]
    highest, lowest = max(bar.high for bar in window), min(bar.low for bar in window)
    if highest <= lowest:
        return None
    return -100.0 * (highest - bars[index].close) / (highest - lowest)


def events_for_symbol(symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels, atr = label_completed_4h_bars(bars), wilder_atr(daily, 14)
    events: list[dict[str, Any]] = []
    next_allowed = 0
    for index in range(LOOKBACK, len(daily) - 8):
        value = williams_r(daily, index)
        signal_ts = daily[index].ts + DAY_MS
        if value is None or signal_ts < next_allowed or split(signal_ts) is None or atr[index - 1] is None:
            continue
        direction = "long" if value <= LOW_THRESHOLD else "short" if value >= HIGH_THRESHOLD else None
        if direction is None or regime_at_entry(labels, signal_ts) != RANGE_REGIME:
            continue
        exit_ts = next(
            (
                daily[j].ts + DAY_MS
                for j in range(index + 1, min(index + 8, len(daily)))
                if (future_value := williams_r(daily, j)) is not None
                and (
                    (direction == "long" and future_value >= MIDPOINT)
                    or (direction == "short" and future_value <= MIDPOINT)
                )
            ),
            None,
        )
        event = trade_event(symbol, RULE_ID, direction, signal_ts + FOUR_HOURS_MS, bars, float(atr[index - 1]), exit_ts,
                            7 * DAY_MS, OOS_END, RANGE_REGIME)
        if event is None:
            continue
        event["split"] = split(signal_ts)
        event["trigger_metrics"] = {"williams_r_14": round(value, 6)}
        events.append(event)
        next_allowed = event["exit_ts"] + 900_000
    return events


def summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(event["net_return_pct"]) for event in events]
    by_month: dict[str, float] = defaultdict(float)
    for event in events:
        if event["net_return_pct"] > 0:
            month = datetime.fromtimestamp(event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")
            by_month[month] += float(event["net_return_pct"])
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
    return {"report_type": "daily_williams_r_range_reversion_audit", "rule_id": RULE_ID,
            "parameters": {"lookback": LOOKBACK, "long_threshold": LOW_THRESHOLD, "short_threshold": HIGH_THRESHOLD, "exit_midpoint": MIDPOINT, "entry_delay_hours": 4, "stop_atr_multiple": 2.0, "max_horizon_days": 7, "friction_pct": 0.16},
            "formation": formation, "oos": oos, "events": events, "status": status, "reasons": reasons,
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_williams_r_range_reversion_audit.json"))
    args = parser.parse_args()
    report = build(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['events']}; oos={report['oos']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
