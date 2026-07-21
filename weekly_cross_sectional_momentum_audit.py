"""Observed audit for a frozen weekly cross-sectional momentum portfolio."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daily_volume_shock_reversal_audit import LATE_FOLDS, PRIMARY_START, late_constant_symbols
from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from low_volatility_drift_fixed_risk_audit import load_price_maps
from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DATA_END, DAY_MS, eligible_symbols, load_json, parse_day, trade_event, wilder_atr
from two_regime_shared_capital_combo_simulation import component_attribution


LOOKBACK_DAYS = 28
LONG_COUNT = 3
SHORT_COUNT = 3
HOLD_DAYS = 7
POSITION_FRACTION = 0.10
MAX_POSITIONS = 6
BASE_COMPONENT = "weekly_cross_sectional_momentum_v1"
LONG_COMPONENT = f"{BASE_COMPONENT}_long"
SHORT_COMPONENT = f"{BASE_COMPONENT}_short"
COMPONENTS = (LONG_COMPONENT, SHORT_COMPONENT)


def is_monday_utc(ts: int) -> bool:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).weekday() == 0


def select_ranked(scores: dict[str, float]) -> tuple[list[str], list[str]]:
    ranked = sorted(scores, key=lambda symbol: (scores[symbol], symbol))
    shorts = ranked[:SHORT_COUNT]
    longs = list(reversed(ranked[-LONG_COUNT:]))
    return longs, shorts


def build_daily_inputs(
    data_dir: Path, symbols: list[str]
) -> tuple[dict[str, list[Bar]], dict[str, list[Bar]], dict[str, list[float | None]]]:
    bars_15m: dict[str, list[Bar]] = {}
    daily: dict[str, list[Bar]] = {}
    atr: dict[str, list[float | None]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        daily_bars = resample_minutes(bars, 1440)
        bars_15m[symbol] = bars
        daily[symbol] = daily_bars
        atr[symbol] = wilder_atr(daily_bars, 14)
    return bars_15m, daily, atr


def generate_events(data_dir: Path, symbols: list[str], start_ts: int, end_ts: int) -> list[dict[str, Any]]:
    bars_15m, daily_by_symbol, atr_by_symbol = build_daily_inputs(data_dir, symbols)
    index_by_symbol = {
        symbol: {bar.ts: index for index, bar in enumerate(daily)}
        for symbol, daily in daily_by_symbol.items()
    }
    reference = daily_by_symbol[symbols[0]] if symbols else []
    events: list[dict[str, Any]] = []
    for reference_bar in reference:
        signal_ts = reference_bar.ts + DAY_MS
        if not start_ts <= signal_ts <= end_ts or not is_monday_utc(signal_ts):
            continue
        completed_day_ts = signal_ts - DAY_MS
        lookback_ts = completed_day_ts - LOOKBACK_DAYS * DAY_MS
        scores: dict[str, float] = {}
        for symbol in symbols:
            current_index = index_by_symbol[symbol].get(completed_day_ts)
            prior_index = index_by_symbol[symbol].get(lookback_ts)
            if current_index is None or prior_index is None:
                continue
            current = daily_by_symbol[symbol][current_index]
            prior = daily_by_symbol[symbol][prior_index]
            if prior.close > 0 and atr_by_symbol[symbol][current_index] is not None:
                scores[symbol] = current.close / prior.close - 1.0
        if len(scores) != len(symbols):
            continue
        longs, shorts = select_ranked(scores)
        selections = [(symbol, "long") for symbol in longs] + [(symbol, "short") for symbol in shorts]
        for priority, (symbol, direction) in enumerate(selections):
            current_index = index_by_symbol[symbol][completed_day_ts]
            signal_atr = atr_by_symbol[symbol][current_index]
            if signal_atr is None:
                continue
            component = LONG_COMPONENT if direction == "long" else SHORT_COMPONENT
            event = trade_event(
                symbol,
                component,
                direction,
                signal_ts,
                bars_15m[symbol],
                float(signal_atr),
                None,
                HOLD_DAYS * DAY_MS,
                end_ts,
                "weekly_cross_sectional_rank",
            )
            if event is not None:
                event.update(
                    {
                        "ranking_return_28d": round(scores[symbol], 8),
                        "ranking_position": priority + 1,
                        "portfolio_priority": float(priority),
                    }
                )
                events.append(event)
    return events


def fold_events(events: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    start_ts = parse_day(start)
    end_ts = parse_day(end, end=True)
    return [
        event for event in events
        if start_ts <= int(event["entry_ts"]) <= end_ts and int(event["exit_ts"]) <= end_ts
    ]


def run_portfolio(events: list[dict[str, Any]], price_maps: dict[str, dict[int, Bar]]) -> dict[str, Any]:
    result = simulate_portfolio(
        events,
        price_maps,
        initial_capital=100_000.0,
        max_positions=MAX_POSITIONS,
        position_fraction=POSITION_FRACTION,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
    )
    result["sleeve_attribution"] = component_attribution(result, COMPONENTS)
    return result


def outcome_reasons(aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if int(aggregate.get("accepted_positions", 0)) < 240:
        reasons.append(f"accepted positions {aggregate.get('accepted_positions', 0)} < 240")
    if float(aggregate.get("total_return_pct", 0.0)) <= 0:
        reasons.append(f"aggregate return {aggregate.get('total_return_pct', 0.0):+.6f}% <= 0%")
    if float(aggregate.get("max_drawdown_pct", 0.0)) > 20.0:
        reasons.append(f"maximum drawdown {aggregate['max_drawdown_pct']:.6f}% > 20%")
    positive_folds = sum(float(result.get("total_return_pct", 0.0)) > 0 for result in folds.values())
    if positive_folds < 2:
        reasons.append(f"positive folds {positive_folds}/3 < 2/3")
    if float(aggregate.get("top_positive_month_share", 0.0)) > 0.25:
        reasons.append(f"top positive month share {aggregate['top_positive_month_share']:.2%} > 25%")
    attribution = aggregate.get("sleeve_attribution", {})
    for component in COMPONENTS:
        item = attribution.get(component, {})
        if int(item.get("accepted_positions", 0)) < 100:
            reasons.append(f"{component} accepted positions {item.get('accepted_positions', 0)} < 100")
        if float(item.get("return_contribution_pct", 0.0)) <= 0:
            reasons.append(
                f"{component} return contribution {item.get('return_contribution_pct', 0.0):+.6f}% <= 0%"
            )
    return reasons


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "candidate_events",
            "accepted_positions",
            "capacity_rejected_events",
            "total_return_pct",
            "max_drawdown_pct",
            "realized_win_rate",
            "average_gross_exposure",
            "peak_gross_exposure",
            "capital_turnover",
            "top_positive_month_share",
            "sleeve_attribution",
        )
    }


def posthoc_sleeve_watchlist(
    aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    watchlist: list[dict[str, Any]] = []
    for component in COMPONENTS:
        item = aggregate.get("sleeve_attribution", {}).get(component, {})
        positive_folds = sum(
            float(result.get("sleeve_attribution", {}).get(component, {}).get("return_contribution_pct", 0.0)) > 0
            for result in folds.values()
        )
        if (
            int(item.get("accepted_positions", 0)) >= 100
            and float(item.get("return_contribution_pct", 0.0)) > 0
            and positive_folds >= 2
        ):
            watchlist.append(
                {
                    "component_id": component,
                    "accepted_positions": int(item["accepted_positions"]),
                    "return_contribution_pct": float(item["return_contribution_pct"]),
                    "positive_fold_count": positive_folds,
                    "status": "posthoc_sleeve_weak_feature_watchlist",
                    "allowed_as_standalone": False,
                }
            )
    return watchlist


def build_report(coverage: dict[str, Any], universe: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = late_constant_symbols(universe)
    start_ts = parse_day(PRIMARY_START)
    end_ts = parse_day(DATA_END, end=True)
    events = generate_events(data_dir, symbols, start_ts, end_ts)
    price_maps = load_price_maps(data_dir, eligible_symbols(coverage))
    aggregate = run_portfolio(events, price_maps)
    folds = {
        name: run_portfolio(fold_events(events, start, end), price_maps)
        for name, start, end in LATE_FOLDS
    }
    reasons = outcome_reasons(aggregate, folds)
    sleeve_watchlist = posthoc_sleeve_watchlist(aggregate, folds)
    short_events = [event for event in events if event["component_id"] == SHORT_COMPONENT]
    short_aggregate = run_portfolio(short_events, price_maps)
    short_folds = {
        name: run_portfolio(fold_events(short_events, start, end), price_maps)
        for name, start, end in LATE_FOLDS
    }
    return {
        "report_type": "weekly_cross_sectional_momentum_audit",
        "report_date": "2026-07-14",
        "research_id": BASE_COMPONENT,
        "scope": "observed_constant_universe_weekly_portfolio_audit",
        "window": {"start": PRIMARY_START, "end": DATA_END},
        "constant_symbols": symbols,
        "constant_symbol_count": len(symbols),
        "frozen_rules": {
            "lookback_days": LOOKBACK_DAYS,
            "rebalance": "Monday 00:00 UTC",
            "long_count": LONG_COUNT,
            "short_count": SHORT_COUNT,
            "hold_days": HOLD_DAYS,
            "stop_atr_multiple": 2.0,
            "round_trip_cost_pct": 0.16,
            "position_fraction": POSITION_FRACTION,
            "max_positions": MAX_POSITIONS,
        },
        "event_direction_counts": dict(Counter(str(event["direction"]) for event in events)),
        "aggregate": summarize_result(aggregate),
        "folds": {name: summarize_result(result) for name, result in folds.items()},
        "positive_fold_count": sum(float(result["total_return_pct"]) > 0 for result in folds.values()),
        "outcome_reasons": reasons,
        "status": "frozen_prospective_candidate" if not reasons else "observed_rejected",
        "posthoc_sleeve_weak_feature_watchlist": sleeve_watchlist,
        "posthoc_short_standalone_diagnostic": {
            "aggregate": summarize_result(short_aggregate),
            "folds": {name: summarize_result(result) for name, result in short_folds.items()},
            "positive_fold_count": sum(float(result["total_return_pct"]) > 0 for result in short_folds.values()),
            "status": "posthoc_weak_feature_diagnostic_not_candidate",
        },
        "prospective_validation_required": not reasons,
        "methodology_notes": [
            "The rule is cross-sectional long-short and differs from rejected BTC/ETH time-series long-only momentum.",
            "All ranking inputs are completed before Monday entry.",
            "The same constant 28-symbol universe is used in all three folds.",
            "All observations stop at 2026-07-10; prospective signals and returns are not read.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    result = report["aggregate"]
    lines = [
        "# Weekly Cross-Sectional Momentum Audit",
        "",
        "Date: 2026-07-14",
        "",
        "Constant 28-symbol, weekly long-short observed audit.",
        "",
        "## Aggregate",
        "",
        f"- candidate events: {result['candidate_events']}",
        f"- accepted positions: {result['accepted_positions']}",
        f"- return: {result['total_return_pct']:+.6f}%",
        f"- maximum drawdown: {result['max_drawdown_pct']:.6f}%",
        f"- win rate: {result['realized_win_rate']:.2%}",
        f"- average / peak exposure: {result['average_gross_exposure']:.2%} / {result['peak_gross_exposure']:.2%}",
        f"- capital turnover: {result['capital_turnover']:.4f}x",
        f"- positive folds: {report['positive_fold_count']}/3",
        f"- top positive month share: {result['top_positive_month_share']:.2%}",
        "",
        "## Fold Returns",
        "",
        "| 2025-H1 | 2025-H2 | 2026-H1 |",
        "| ---: | ---: | ---: |",
        "| " + " | ".join(f"{report['folds'][name]['total_return_pct']:+.6f}%" for name, _s, _e in LATE_FOLDS) + " |",
        "",
        "## Sleeve Attribution",
        "",
        "| Sleeve | Accepted | Rejected | Return Contribution | Win |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for component, item in result["sleeve_attribution"].items():
        lines.append(
            f"| `{component}` | {item['accepted_positions']} | {item['rejected_events']} | "
            f"{item['return_contribution_pct']:+.6f}% | {item['realized_win_rate']:.2%} |"
        )
    lines.extend(["", "## Decision", ""])
    if report["outcome_reasons"]:
        lines.extend(f"- {reason}" for reason in report["outcome_reasons"])
    else:
        lines.append("- Observed screen passed; freeze unchanged for prospective validation.")
    if report["posthoc_sleeve_weak_feature_watchlist"]:
        lines.extend(["", "## Post-Hoc Sleeve Watchlist", ""])
        for item in report["posthoc_sleeve_weak_feature_watchlist"]:
            lines.append(
                f"- `{item['component_id']}`: {item['accepted_positions']} accepted, "
                f"{item['return_contribution_pct']:+.6f}% contribution, "
                f"{item['positive_fold_count']}/3 positive folds; standalone use prohibited."
            )
        short_result = report["posthoc_short_standalone_diagnostic"]["aggregate"]
        lines.extend(
            [
                "",
                f"Short-only diagnostic: {short_result['accepted_positions']} accepted, "
                f"{short_result['total_return_pct']:+.6f}% return, "
                f"{short_result['max_drawdown_pct']:.6f}% max DD, "
                f"{report['posthoc_short_standalone_diagnostic']['positive_fold_count']}/3 positive folds, "
                f"{short_result['top_positive_month_share']:.2%} month concentration.",
            ]
        )
    lines.extend(
        [
            "",
            f"Status: `{report['status']}`.",
            "",
            "## Safety",
            "",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit frozen weekly cross-sectional momentum.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/weekly_cross_sectional_momentum_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/weekly_cross_sectional_momentum_audit_2026-07-14.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), load_json(args.universe), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    result = report["aggregate"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
        f"dd={result['max_drawdown_pct']:.6f}%, folds={report['positive_fold_count']}/3, "
        f"status={report['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
