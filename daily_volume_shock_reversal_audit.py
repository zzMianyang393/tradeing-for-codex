"""Observed outcome audit for the frozen daily volume-shock reversal rule."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from daily_volume_shock_reversal_preflight import (
    ATR_PERIOD,
    RANGE_ATR_MULTIPLE,
    VOLUME_LOOKBACK,
    VOLUME_MULTIPLE,
    event_direction,
    true_range,
)
from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from low_volatility_drift_fixed_risk_audit import load_price_maps
from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DATA_END, DATA_START, DAY_MS, FOLDS, eligible_symbols, load_json, parse_day, trade_event, wilder_atr
from two_regime_shared_capital_combo_simulation import component_attribution


BASE_COMPONENT = "daily_volume_shock_reversal_v1"
LONG_COMPONENT = f"{BASE_COMPONENT}_long"
SHORT_COMPONENT = f"{BASE_COMPONENT}_short"
COMPONENTS = (LONG_COMPONENT, SHORT_COMPONENT)
LATE_FOLDS = FOLDS[2:]
PRIMARY_START = "2025-01-01"
POSITION_FRACTION = 0.10
MAX_POSITIONS = 5


def late_constant_symbols(universe: dict[str, Any]) -> list[str]:
    eligible_sets = [
        set(str(symbol) for symbol in universe["eligible_symbols_by_fold"][name])
        for name, _start, _end in LATE_FOLDS
    ]
    return sorted(set.intersection(*eligible_sets)) if eligible_sets else []


def generate_symbol_events(
    symbol: str,
    bars_15m: list[Bar],
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    daily = resample_minutes(bars_15m, 1440)
    atr_values = wilder_atr(daily, ATR_PERIOD)
    events: list[dict[str, Any]] = []
    next_available = 0
    for index in range(max(VOLUME_LOOKBACK, ATR_PERIOD) + 1, len(daily)):
        signal_ts = daily[index].ts + DAY_MS
        if not start_ts <= signal_ts <= end_ts or signal_ts < next_available:
            continue
        prior_atr = atr_values[index - 1]
        prior_volume = mean(float(bar.volume_quote) for bar in daily[index - VOLUME_LOOKBACK:index])
        current = daily[index]
        daily_range = current.high - current.low
        if prior_atr is None or prior_atr <= 0 or prior_volume <= 0 or daily_range <= 0:
            continue
        volume_ratio = float(current.volume_quote) / prior_volume
        range_ratio = true_range(current, daily[index - 1].close) / float(prior_atr)
        close_location = (current.close - current.low) / daily_range
        direction = event_direction(close_location)
        if volume_ratio < VOLUME_MULTIPLE or range_ratio < RANGE_ATR_MULTIPLE or direction is None:
            continue
        component = LONG_COMPONENT if direction == "long" else SHORT_COMPONENT
        event = trade_event(
            symbol,
            component,
            direction,
            signal_ts,
            bars_15m,
            float(prior_atr),
            None,
            3 * DAY_MS,
            end_ts,
            "daily_volume_shock_exhaustion",
        )
        if event is not None:
            event.update(
                {
                    "volume_ratio": round(volume_ratio, 6),
                    "range_atr_ratio": round(range_ratio, 6),
                    "close_location": round(close_location, 6),
                }
            )
            events.append(event)
            next_available = int(event["exit_ts"]) + 15 * 60 * 1000
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
    result["direction_attribution"] = component_attribution(result, COMPONENTS)
    return result


def outcome_reasons(aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if int(aggregate.get("accepted_positions", 0)) < 60:
        reasons.append(f"accepted positions {aggregate.get('accepted_positions', 0)} < 60")
    if float(aggregate.get("total_return_pct", 0.0)) <= 0:
        reasons.append(f"aggregate return {aggregate.get('total_return_pct', 0.0):+.6f}% <= 0%")
    if float(aggregate.get("max_drawdown_pct", 0.0)) > 20.0:
        reasons.append(f"maximum drawdown {aggregate['max_drawdown_pct']:.6f}% > 20%")
    positive_folds = sum(float(result.get("total_return_pct", 0.0)) > 0 for result in folds.values())
    if positive_folds < 2:
        reasons.append(f"positive folds {positive_folds}/3 < 2/3")
    if float(aggregate.get("top_positive_month_share", 0.0)) > 0.25:
        reasons.append(f"top positive month share {aggregate['top_positive_month_share']:.2%} > 25%")
    attribution = aggregate.get("direction_attribution", {})
    for component in COMPONENTS:
        item = attribution.get(component, {})
        if int(item.get("accepted_positions", 0)) < 20:
            reasons.append(f"{component} accepted positions {item.get('accepted_positions', 0)} < 20")
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
            "direction_attribution",
        )
    }


def posthoc_direction_watchlist(
    aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    watchlist: list[dict[str, Any]] = []
    for component in COMPONENTS:
        item = aggregate.get("direction_attribution", {}).get(component, {})
        positive_folds = sum(
            float(result.get("direction_attribution", {}).get(component, {}).get("return_contribution_pct", 0.0)) > 0
            for result in folds.values()
        )
        if (
            int(item.get("accepted_positions", 0)) >= 30
            and float(item.get("return_contribution_pct", 0.0)) > 0
            and positive_folds >= 2
        ):
            watchlist.append(
                {
                    "component_id": component,
                    "accepted_positions": int(item["accepted_positions"]),
                    "return_contribution_pct": float(item["return_contribution_pct"]),
                    "positive_fold_count": positive_folds,
                    "status": "posthoc_directional_weak_feature_watchlist",
                    "allowed_as_standalone": False,
                    "prospective_validation_required": True,
                }
            )
    return watchlist


def build_report(coverage: dict[str, Any], universe: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    all_symbols = eligible_symbols(coverage)
    primary_symbols = late_constant_symbols(universe)
    full_constant_symbols = sorted(str(symbol) for symbol in universe["constant_full_window_symbols"])
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
    events_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for symbol in all_symbols:
        base = symbol.split("-", 1)[0]
        events_by_symbol[symbol] = generate_symbol_events(
            symbol,
            load_quantify_15m_csv(data_dir / f"{base}_15m.csv"),
            start_ts,
            end_ts,
        )
    price_maps = load_price_maps(data_dir, all_symbols)
    primary_events = [
        event for symbol in primary_symbols for event in events_by_symbol[symbol]
        if int(event["entry_ts"]) >= parse_day(PRIMARY_START)
    ]
    primary_aggregate = run_portfolio(primary_events, price_maps)
    primary_folds = {
        name: run_portfolio(fold_events(primary_events, start, end), price_maps)
        for name, start, end in LATE_FOLDS
    }
    reasons = outcome_reasons(primary_aggregate, primary_folds)
    direction_watchlist = posthoc_direction_watchlist(primary_aggregate, primary_folds)
    short_events = [event for event in primary_events if event["component_id"] == SHORT_COMPONENT]
    short_aggregate = run_portfolio(short_events, price_maps)
    short_folds = {
        name: run_portfolio(fold_events(short_events, start, end), price_maps)
        for name, start, end in LATE_FOLDS
    }
    secondary_events = [
        event for symbol in full_constant_symbols for event in events_by_symbol[symbol]
    ]
    secondary = run_portfolio(secondary_events, price_maps)
    return {
        "report_type": "daily_volume_shock_reversal_audit",
        "report_date": "2026-07-13",
        "research_id": BASE_COMPONENT,
        "scope": "observed_outcome_audit_after_return_free_preflight",
        "primary_window": {"start": PRIMARY_START, "end": DATA_END},
        "primary_constant_symbols": primary_symbols,
        "primary_constant_symbol_count": len(primary_symbols),
        "primary_aggregate": summarize_result(primary_aggregate),
        "primary_folds": {name: summarize_result(result) for name, result in primary_folds.items()},
        "primary_positive_fold_count": sum(float(result["total_return_pct"]) > 0 for result in primary_folds.values()),
        "secondary_full_window_btc_eth": summarize_result(secondary),
        "outcome_reasons": reasons,
        "status": "frozen_prospective_candidate" if not reasons else "observed_rejected",
        "posthoc_directional_weak_feature_watchlist": direction_watchlist,
        "posthoc_short_standalone_diagnostic": {
            "aggregate": summarize_result(short_aggregate),
            "folds": {name: summarize_result(result) for name, result in short_folds.items()},
            "positive_fold_count": sum(float(result["total_return_pct"]) > 0 for result in short_folds.values()),
            "status": "posthoc_weak_feature_diagnostic_not_candidate",
        },
        "prospective_validation_required": not reasons,
        "parameters_changed_after_preflight": False,
        "methodology_notes": [
            "The signal was frozen after an event-only preflight that contained no forward returns.",
            "The 2025+ primary window uses the intersection of symbols eligible in all three late folds.",
            "The BTC/ETH full-window panel is descriptive only because it has eight preflight events.",
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
    result = report["primary_aggregate"]
    lines = [
        "# Daily Volume-Shock Reversal Audit",
        "",
        "Date: 2026-07-13",
        "",
        "The signal was frozen after a return-free event preflight.",
        "",
        "## Primary Constant-Universe Result",
        "",
        f"- symbols: {report['primary_constant_symbol_count']}",
        f"- accepted positions: {result['accepted_positions']}",
        f"- return: {result['total_return_pct']:+.6f}%",
        f"- maximum drawdown: {result['max_drawdown_pct']:.6f}%",
        f"- win rate: {result['realized_win_rate']:.2%}",
        f"- average / peak exposure: {result['average_gross_exposure']:.2%} / {result['peak_gross_exposure']:.2%}",
        f"- positive folds: {report['primary_positive_fold_count']}/3",
        f"- top positive month share: {result['top_positive_month_share']:.2%}",
        "",
        "## Fold Returns",
        "",
        "| 2025-H1 | 2025-H2 | 2026-H1 |",
        "| ---: | ---: | ---: |",
        "| " + " | ".join(f"{report['primary_folds'][name]['total_return_pct']:+.6f}%" for name, _s, _e in LATE_FOLDS) + " |",
        "",
        "## Direction Attribution",
        "",
        "| Direction | Accepted | Rejected | Return Contribution | Win |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for component, item in result["direction_attribution"].items():
        lines.append(
            f"| `{component}` | {item['accepted_positions']} | {item['rejected_events']} | "
            f"{item['return_contribution_pct']:+.6f}% | {item['realized_win_rate']:.2%} |"
        )
    lines.extend(["", "## Decision", ""])
    if report["outcome_reasons"]:
        lines.extend(f"- {reason}" for reason in report["outcome_reasons"])
    else:
        lines.append("- Observed screen passed; freeze unchanged for prospective validation.")
    if report["posthoc_directional_weak_feature_watchlist"]:
        lines.extend(["", "## Post-Hoc Direction Watchlist", ""])
        for item in report["posthoc_directional_weak_feature_watchlist"]:
            lines.append(
                f"- `{item['component_id']}`: {item['accepted_positions']} accepted, "
                f"{item['return_contribution_pct']:+.6f}% contribution, "
                f"{item['positive_fold_count']}/3 positive folds; standalone use prohibited."
            )
        short_result = report["posthoc_short_standalone_diagnostic"]["aggregate"]
        lines.extend(
            [
                "",
                f"Short-only shared-capital diagnostic: {short_result['accepted_positions']} accepted, "
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
    parser = argparse.ArgumentParser(description="Audit the frozen daily volume-shock reversal candidate.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/daily_volume_shock_reversal_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/daily_volume_shock_reversal_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), load_json(args.universe), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    result = report["primary_aggregate"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
        f"dd={result['max_drawdown_pct']:.6f}%, folds={report['primary_positive_fold_count']}/3, "
        f"status={report['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
