"""Fixed-parameter historical audit for Cohort B high-volatility hypotheses."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DAY_MS, parse_day, wilder_atr
from regime_validation import label_completed_4h_bars, regime_at_entry


ATR_PERIOD = 20
ROUND_TRIP_COST_PCT = 0.16
FORMATION_START = "2024-01-01"
FORMATION_END = "2024-12-31"
OOS_START = "2025-01-01"
OOS_END = "2025-07-10"
HIGH_VOLATILITY = "高波动转换"


def _true_range(current: Bar, prior_close: float) -> float:
    return max(current.high - current.low, abs(current.high - prior_close), abs(current.low - prior_close))


def _split(ts: int) -> str | None:
    if parse_day(FORMATION_START) <= ts <= parse_day(FORMATION_END, end=True):
        return "formation"
    if parse_day(OOS_START) <= ts <= parse_day(OOS_END, end=True):
        return "oos"
    return None


def _event(symbol: str, rule: str, direction: str, signal_ts: int, bars: list[Bar], atr: float, metrics: dict[str, float]) -> dict[str, Any] | None:
    hold_days = 7 if rule == "daily_volatility_expansion_continuation_v1" else 5
    entry_index = next((i for i, bar in enumerate(bars) if bar.ts >= signal_ts + 4 * 60 * 60 * 1000), None)
    if entry_index is None or entry_index + hold_days * 96 >= len(bars) or atr <= 0:
        return None
    entry = bars[entry_index]
    exit_bar = bars[entry_index + hold_days * 96]
    gross = exit_bar.open / entry.open - 1.0 if direction == "long" else entry.open / exit_bar.open - 1.0
    return {
        "symbol": symbol, "rule_id": rule, "direction": direction, "signal_ts": signal_ts,
        "entry_regime": HIGH_VOLATILITY, "gross_return_pct": round(gross * 100, 6),
        "net_return_pct": round(gross * 100 - ROUND_TRIP_COST_PCT, 6), "metrics": metrics,
    }


def generate_events(symbol: str, bars: list[Bar], rule: str) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels = label_completed_4h_bars(bars)
    atrs = wilder_atr(daily, ATR_PERIOD)
    events: list[dict[str, Any]] = []
    for i in range(max(ATR_PERIOD, 20), len(daily) - 6):
        atr = atrs[i - 1]
        if atr is None or atr <= 0:
            continue
        current = daily[i]
        signal_ts = current.ts + DAY_MS
        split = _split(signal_ts)
        if split is None or regime_at_entry(labels, signal_ts) != HIGH_VOLATILITY:
            continue
        daily_range = current.high - current.low
        if daily_range <= 0:
            continue
        direction: str | None = None
        metrics: dict[str, float] = {}
        if rule == "daily_volatility_expansion_continuation_v1":
            tr_ratio = _true_range(current, daily[i - 1].close) / atr
            location = (current.close - current.low) / daily_range
            if tr_ratio >= 1.8 and location >= 0.75:
                direction = "long"
            elif tr_ratio >= 1.8 and location <= 0.25:
                direction = "short"
            metrics = {"true_range_atr_ratio": round(tr_ratio, 6), "close_location": round(location, 6)}
        elif rule == "daily_failed_breakout_reversal_v1":
            channel_high = max(bar.high for bar in daily[i - 20:i])
            wick_share = (current.high - current.close) / daily_range
            distance_atr = (current.high - channel_high) / atr
            if distance_atr >= 0.25 and current.close < channel_high and wick_share >= 0.40:
                direction = "short"
            metrics = {"breakout_distance_atr": round(distance_atr, 6), "upper_wick_share": round(wick_share, 6)}
        else:
            raise ValueError(f"unknown rule: {rule}")
        if direction:
            item = _event(symbol, rule, direction, signal_ts, bars, float(atr), metrics)
            if item:
                item["split"] = split
                events.append(item)
    return events


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(item["net_return_pct"]) for item in events]
    return {"events": len(events), "net_sum_pct": round(sum(values), 6), "mean_pct": round(mean(values), 6) if values else 0.0,
            "median_pct": round(median(values), 6) if values else 0.0,
            "win_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
            "directions": dict(sorted(Counter(str(item["direction"]) for item in events).items()))}


def build_report(data_dir: Path, symbols: list[str]) -> dict[str, Any]:
    rules = ("daily_volatility_expansion_continuation_v1", "daily_failed_breakout_reversal_v1")
    rule_reports: dict[str, Any] = {}
    for rule in rules:
        events = [event for symbol in symbols for event in generate_events(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"), rule)]
        formation = [event for event in events if event["split"] == "formation"]
        oos = [event for event in events if event["split"] == "oos"]
        reasons = []
        for name, group in (("formation", formation), ("oos", oos)):
            if len(group) < 15:
                reasons.append(f"{name} compatible events {len(group)} < 15")
        insufficient_evidence = len(formation) < 15 or len(oos) < 15
        if summarize(formation)["mean_pct"] <= 0 or summarize(oos)["mean_pct"] <= 0:
            reasons.append("one or more fixed windows has non-positive mean net return")
        rule_reports[rule] = {"formation": summarize(formation), "oos": summarize(oos), "events": events,
                              "status": "insufficient_evidence" if insufficient_evidence else ("historical_research_candidate" if not reasons else "historical_rejected"),
                              "reasons": reasons}
    return {"report_type": "daily_high_volatility_transition_audit", "scope": "historical_regime_conditioned_research",
            "parameters": {"atr_period": ATR_PERIOD, "friction_pct": ROUND_TRIP_COST_PCT, "entry_delay_hours": 4,
                           "hold_days_by_rule": {"daily_volatility_expansion_continuation_v1": 7, "daily_failed_breakout_reversal_v1": 5}},
            "rules": rule_reports, "outcomes_evaluated": True,
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    parser.add_argument("--out", type=Path, default=Path("reports/daily_high_volatility_transition_audit.json"))
    args = parser.parse_args()
    report = build_report(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for rule, result in report["rules"].items():
        print(f"{rule}: formation={result['formation']['events']}, oos={result['oos']['events']}, status={result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
