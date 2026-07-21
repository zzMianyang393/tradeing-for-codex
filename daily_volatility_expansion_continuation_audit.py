"""Frozen historical audit for the Cohort B volatility-expansion research card."""
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

RULE_ID = "daily_volatility_expansion_continuation_v1"
HIGH_VOL_TRANSITION = "\u9ad8\u6ce2\u52a8\u8f6c\u6362"
ATR_PERIOD = 20
EXPANSION_MULTIPLE = 1.80
MAX_HORIZON_MS = 7 * DAY_MS
OOS_END = parse_day("2025-07-10", end=True)


def split(ts: int) -> str | None:
    if parse_day("2024-01-01") <= ts <= parse_day("2024-12-31", end=True):
        return "formation"
    if parse_day("2025-01-01") <= ts <= OOS_END:
        return "oos"
    return None


def true_range(bar: Bar, previous_close: float) -> float:
    return max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))


def signal_candidates(symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels = label_completed_4h_bars(bars)
    atr = wilder_atr(daily, ATR_PERIOD)
    events: list[dict[str, Any]] = []
    next_allowed_ts = 0
    for index in range(ATR_PERIOD + 1, len(daily) - 8):
        bar, previous = daily[index], daily[index - 1]
        signal_ts = bar.ts + DAY_MS
        if signal_ts < next_allowed_ts or split(signal_ts) is None or atr[index - 1] is None:
            continue
        daily_range = bar.high - bar.low
        if daily_range <= 0 or true_range(bar, previous.close) < EXPANSION_MULTIPLE * float(atr[index - 1]):
            continue
        close_location = (bar.close - bar.low) / daily_range
        direction = "long" if close_location >= 0.75 else "short" if close_location <= 0.25 else None
        if direction is None:
            continue
        regime = regime_at_entry(labels, signal_ts)
        event = trade_event(symbol, RULE_ID, direction, signal_ts + FOUR_HOURS_MS, bars, float(atr[index - 1]), None,
                            MAX_HORIZON_MS, OOS_END, regime)
        if event is None:
            continue
        event["split"] = split(signal_ts)
        event["regime_compatible"] = regime == HIGH_VOL_TRANSITION
        event["trigger_metrics"] = {
            "true_range_to_prior_atr": round(true_range(bar, previous.close) / float(atr[index - 1]), 6),
            "close_location": round(close_location, 6),
        }
        events.append(event)
        next_allowed_ts = event["exit_ts"] + 900_000
    return events


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(event["net_return_pct"]) for event in events]
    positives: dict[str, float] = defaultdict(float)
    for event in events:
        if event["net_return_pct"] > 0:
            month = datetime.fromtimestamp(event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")
            positives[month] += float(event["net_return_pct"])
    total_positive = sum(positives.values())
    concentration = max(positives.values()) / total_positive if total_positive else 0.0
    november = positives.get("2024-11", 0.0) / total_positive if total_positive else 0.0
    without_november = [event["net_return_pct"] for event in events if datetime.fromtimestamp(
        event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m") != "2024-11"]
    return {
        "events": len(events), "net_sum_pct": round(sum(values), 6),
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "win_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
        "positive_return_month_concentration": round(concentration, 6),
        "november_2024_positive_return_contribution": round(november, 6),
        "excluding_2024_11_net_sum_pct": round(sum(without_november), 6),
        "excluding_2024_11_mean_pct": round(mean(without_november), 6) if without_november else 0.0,
    }


def verdict(formation: dict[str, Any], oos: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    insufficient = False
    for name, stats in (("formation", formation), ("oos", oos)):
        if stats["events"] < 15:
            reasons.append(f"{name} compatible events {stats['events']} < 15")
            insufficient = True
        if stats["mean_pct"] <= 0:
            reasons.append(f"{name} compatible mean <= 0")
    if formation["november_2024_positive_return_contribution"] > 0.25 and formation["excluding_2024_11_net_sum_pct"] <= 0:
        reasons.append("formation 2024-11 contribution > 25% and result turns non-positive when 2024-11 is removed")
    return ("insufficient_evidence" if insufficient else "historical_rejected" if reasons else "historical_research_candidate"), reasons


def build(data_dir: Path, symbols: list[str]) -> dict[str, Any]:
    all_events = [event for symbol in symbols for event in signal_candidates(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"))]
    all_events.sort(key=lambda event: (event["signal_ts"], event["symbol"], event["direction"]))
    compatible = [event for event in all_events if event["regime_compatible"]]
    all_stats = {name: summarize([event for event in all_events if event["split"] == name]) for name in ("formation", "oos")}
    compatible_stats = {name: summarize([event for event in compatible if event["split"] == name]) for name in ("formation", "oos")}
    status, reasons = verdict(compatible_stats["formation"], compatible_stats["oos"])
    return {
        "report_type": "daily_volatility_expansion_continuation_audit", "rule_id": RULE_ID,
        "parameters": {"atr_period": ATR_PERIOD, "expansion_multiple": EXPANSION_MULTIPLE, "close_location": [0.25, 0.75], "entry_delay_hours": 4, "max_horizon_days": 7, "friction_pct": 0.16},
        "formation": {"all_signals": all_stats["formation"], "regime_compatible": compatible_stats["formation"]},
        "oos": {"all_signals": all_stats["oos"], "regime_compatible": compatible_stats["oos"]},
        "events": all_events, "status": status, "reasons": reasons,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_volatility_expansion_continuation_audit.json"))
    args = parser.parse_args()
    report = build(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['regime_compatible']['events']}; oos={report['oos']['regime_compatible']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
