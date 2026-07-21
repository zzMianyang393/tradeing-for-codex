"""Frozen historical audit of weekly weakest-coin continuation shorts.

This reuses the existing weekly 28-day rank definition, but evaluates it only
when the selected coin has a completed downtrend regime label.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from daily_volume_shock_reversal_audit import late_constant_symbols
from downtrend_rebound_capital_constrained_simulator import load_price_maps, simulate_portfolio
from market import Bar
from regime_component_walk_forward_audit import DAY_MS, parse_day, trade_event
from regime_validation import label_completed_4h_bars, regime_at_entry
from weekly_cross_sectional_momentum_audit import (
    HOLD_DAYS,
    LOOKBACK_DAYS,
    POSITION_FRACTION,
    SHORT_COMPONENT,
    SHORT_COUNT,
    build_daily_inputs,
    is_monday_utc,
    select_ranked,
)


RULE_ID = "weekly_cross_sectional_momentum_v1_short_downtrend"
FORMATION_START = "2024-08-01"
FORMATION_END = "2024-12-31"
OOS_START = "2025-01-01"
OOS_END = "2025-07-10"
DOWN_TREND = "趋势下行"


def split(ts: int) -> str | None:
    if parse_day(FORMATION_START) <= ts <= parse_day(FORMATION_END, end=True):
        return "formation"
    if parse_day(OOS_START) <= ts <= parse_day(OOS_END, end=True):
        return "oos"
    return None


def generate_events(data_dir: Path, symbols: list[str]) -> list[dict[str, Any]]:
    bars_15m, daily_by_symbol, atr_by_symbol = build_daily_inputs(data_dir, symbols)
    labels_by_symbol = {symbol: label_completed_4h_bars(bars_15m[symbol]) for symbol in symbols}
    indices = {symbol: {bar.ts: index for index, bar in enumerate(bars)} for symbol, bars in daily_by_symbol.items()}
    reference = daily_by_symbol[symbols[0]] if symbols else []
    events: list[dict[str, Any]] = []
    start_ts, end_ts = parse_day(FORMATION_START), parse_day(OOS_END, end=True)
    for reference_bar in reference:
        signal_ts = reference_bar.ts + DAY_MS
        if not start_ts <= signal_ts <= end_ts or not is_monday_utc(signal_ts):
            continue
        completed_ts = signal_ts - DAY_MS
        lookback_ts = completed_ts - LOOKBACK_DAYS * DAY_MS
        scores: dict[str, float] = {}
        for symbol in symbols:
            current_index, prior_index = indices[symbol].get(completed_ts), indices[symbol].get(lookback_ts)
            if current_index is None or prior_index is None:
                continue
            prior = daily_by_symbol[symbol][prior_index].close
            if prior > 0 and atr_by_symbol[symbol][current_index] is not None:
                scores[symbol] = daily_by_symbol[symbol][current_index].close / prior - 1.0
        if len(scores) != len(symbols):
            continue
        _longs, shorts = select_ranked(scores)
        for rank, symbol in enumerate(shorts, start=1):
            if regime_at_entry(labels_by_symbol[symbol], signal_ts) != DOWN_TREND:
                continue
            current_index = indices[symbol][completed_ts]
            event = trade_event(
                symbol, RULE_ID, "short", signal_ts, bars_15m[symbol], float(atr_by_symbol[symbol][current_index]),
                None, HOLD_DAYS * DAY_MS, end_ts, DOWN_TREND,
            )
            if event is not None:
                event.update({
                    "split": split(signal_ts), "ranking_return_28d": round(scores[symbol], 8),
                    "weakness_rank": rank, "component_id": SHORT_COMPONENT, "portfolio_priority": float(rank),
                })
                events.append(event)
    return sorted(events, key=lambda item: (item["entry_ts"], item["weakness_rank"], item["symbol"]))


def summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(event["net_return_pct"]) for event in events]
    positive_by_month: dict[str, float] = defaultdict(float)
    for event in events:
        if event["net_return_pct"] > 0:
            month = datetime.fromtimestamp(event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")
            positive_by_month[month] += float(event["net_return_pct"])
    total = sum(positive_by_month.values())
    return {
        "events": len(events), "net_sum_pct": round(sum(values), 6),
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "win_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
        "positive_return_month_concentration": round(max(positive_by_month.values()) / total, 6) if total else 0.0,
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
    events = generate_events(data_dir, symbols)
    formation_events = [event for event in events if event["split"] == "formation"]
    oos_events = [event for event in events if event["split"] == "oos"]
    formation, oos = summary(formation_events), summary(oos_events)
    status, reasons = verdict(formation, oos)
    price_maps = load_price_maps(data_dir, events)
    portfolio = {
        name: simulate_portfolio(rows, price_maps, initial_capital=100_000.0, max_positions=3, position_fraction=POSITION_FRACTION, priority_mode="event_score_then_symbol", one_position_per_symbol=True)
        for name, rows in (("formation", formation_events), ("oos", oos_events))
    }
    return {
        "report_type": "weekly_cross_sectional_short_downtrend_audit", "rule_id": RULE_ID,
        "scope": "historical_regime_conditioned_weak_factor_audit",
        "windows": {"formation": [FORMATION_START, FORMATION_END], "oos": [OOS_START, OOS_END]},
        "symbols": symbols,
        "parameters": {"lookback_days": LOOKBACK_DAYS, "rebalance": "Monday 00:00 UTC", "short_count": SHORT_COUNT,
                       "hold_days": HOLD_DAYS, "stop_atr_multiple": 2.0, "entry_delay_hours": 0, "friction_pct": 0.16,
                       "required_regime": DOWN_TREND},
        "formation": formation, "oos": oos, "events": events, "portfolio_diagnostics": {
            name: {key: value for key, value in result.items() if key not in {"equity_curve", "closed_positions", "rejected_events"}}
            for name, result in portfolio.items()
        },
        "status": status, "reasons": reasons,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/weekly_cross_sectional_short_downtrend_audit.json"))
    args = parser.parse_args()
    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    report = build(args.data, late_constant_symbols(universe))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['events']}; oos={report['oos']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
