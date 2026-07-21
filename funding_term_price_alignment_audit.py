"""Observed audit for frozen weekly funding-term price alignment."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from daily_volume_shock_reversal_audit import LATE_FOLDS, PRIMARY_START, late_constant_symbols
from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME, SHORT_COMPATIBLE_REGIME
from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from funding_term_price_alignment_preflight import (
    PRICE_LOOKBACK_DAYS,
    SIGNAL_MINUTES_AFTER_MIDNIGHT,
    build_symbol_inputs,
    funding_state,
    is_monday_signal,
)
from low_volatility_drift_fixed_risk_audit import load_price_maps
from market import Bar
from regime_component_walk_forward_audit import (
    DATA_END,
    DAY_MS,
    eligible_symbols,
    load_json,
    parse_day,
    trade_event,
    wilder_atr,
)
from regime_validation import regime_at_entry
from regime_validation_v2 import LOW_VOLATILITY_DRIFT
from two_regime_shared_capital_combo_simulation import component_attribution
from weekly_cross_sectional_momentum_audit import fold_events


BASE_COMPONENT = "funding_term_price_alignment_v1"
LONG_COMPONENT = f"{BASE_COMPONENT}_long"
SHORT_COMPONENT = f"{BASE_COMPONENT}_short"
COMPONENTS = (LONG_COMPONENT, SHORT_COMPONENT)
POSITION_FRACTION = 0.10
MAX_POSITIONS = 5
HOLD_DAYS = 7


def compatible_regimes(direction: str) -> set[str]:
    if direction == "long":
        return {LONG_COMPATIBLE_REGIME, LOW_VOLATILITY_DRIFT}
    if direction == "short":
        return {SHORT_COMPATIBLE_REGIME, LOW_VOLATILITY_DRIFT}
    raise ValueError(f"unsupported direction: {direction}")


def first_incompatible_regime_exit(
    labels: list[tuple[int, str]], signal_ts: int, direction: str
) -> int | None:
    allowed = compatible_regimes(direction)
    for available_ts, label in labels:
        if available_ts > signal_ts and label not in allowed:
            return available_ts
    return None


def normalized_extremeness(state: dict[str, float | str]) -> float:
    current = float(state["current"])
    threshold = (
        float(state["high_threshold"])
        if state["state"] == "high_positive"
        else float(state["low_threshold"])
    )
    return abs(current - threshold) / max(abs(threshold), 1e-8)


def generate_events(data_dir: Path, symbols: list[str], start_ts: int, end_ts: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for symbol in symbols:
        funding_path = data_dir / f"{symbol}_funding.csv"
        if not funding_path.exists():
            continue
        daily, indices, labels, funding = build_symbol_inputs(data_dir, symbol)
        atr = wilder_atr(daily, 14)
        base = symbol.split("-", 1)[0]
        from market import load_quantify_15m_csv

        bars_15m = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        for bar in daily:
            signal_ts = bar.ts + DAY_MS + SIGNAL_MINUTES_AFTER_MIDNIGHT * 60 * 1000
            if not start_ts <= signal_ts <= end_ts or not is_monday_signal(signal_ts):
                continue
            completed_day_ts = signal_ts // DAY_MS * DAY_MS - DAY_MS
            prior_day_ts = completed_day_ts - PRICE_LOOKBACK_DAYS * DAY_MS
            current_index = indices.get(completed_day_ts)
            prior_index = indices.get(prior_day_ts)
            if current_index is None or prior_index is None or atr[current_index] is None:
                continue
            prior_close = daily[prior_index].close
            if prior_close <= 0:
                continue
            price_change = daily[current_index].close / prior_close - 1.0
            state = funding_state(funding, signal_ts)
            if state is None:
                continue
            regime = regime_at_entry(labels, signal_ts)
            direction: str | None = None
            if state["state"] == "high_positive" and price_change > 0 and regime in compatible_regimes("long"):
                direction = "long"
            elif state["state"] == "low_negative" and price_change < 0 and regime in compatible_regimes("short"):
                direction = "short"
            if direction is None:
                continue
            component = LONG_COMPONENT if direction == "long" else SHORT_COMPONENT
            event = trade_event(
                symbol,
                component,
                direction,
                signal_ts,
                bars_15m,
                float(atr[current_index]),
                first_incompatible_regime_exit(labels, signal_ts, direction),
                HOLD_DAYS * DAY_MS,
                end_ts,
                regime,
            )
            if event is not None:
                event.update(
                    {
                        "funding_state": state["state"],
                        "rolling_7d_funding": float(state["current"]),
                        "funding_low_threshold": float(state["low_threshold"]),
                        "funding_high_threshold": float(state["high_threshold"]),
                        "prior_7d_price_change": round(price_change, 8),
                        "funding_extremeness": round(normalized_extremeness(state), 8),
                        "portfolio_priority": -normalized_extremeness(state),
                    }
                )
                events.append(event)
    return events


def grouped_attribution(
    result: dict[str, Any], events: list[dict[str, Any]], field: str
) -> dict[str, Any]:
    event_values = {
        (str(event.get("symbol")), int(event.get("entry_ts", 0)), str(event.get("component_id"))): str(
            event.get(field, "unknown")
        )
        for event in events
    }
    values: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for position in result.get("closed_positions", []):
        key = (
            str(position.get("symbol")),
            int(position.get("entry_ts", 0)),
            str(position.get("component_id")),
        )
        values[event_values.get(key, "unknown")].append(position)
    initial = float(result.get("initial_equity", 100_000.0))
    output: dict[str, Any] = {}
    for name, positions in sorted(values.items()):
        pnl = sum(float(position.get("realized_pnl", 0.0)) for position in positions)
        output[name] = {
            "accepted_positions": len(positions),
            "return_contribution_pct": round(pnl / initial * 100.0, 6) if initial else 0.0,
            "realized_win_rate": round(
                sum(float(position.get("realized_pnl", 0.0)) > 0 for position in positions) / len(positions), 6
            ),
        }
    return output


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
    result["regime_attribution"] = grouped_attribution(result, events, "entry_regime")
    return result


def outcome_reasons(aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if int(aggregate.get("accepted_positions", 0)) < 120:
        reasons.append(f"accepted positions {aggregate.get('accepted_positions', 0)} < 120")
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
        if int(item.get("accepted_positions", 0)) < 40:
            reasons.append(f"{component} accepted positions {item.get('accepted_positions', 0)} < 40")
        if float(item.get("return_contribution_pct", 0.0)) <= 0:
            reasons.append(
                f"{component} return contribution {item.get('return_contribution_pct', 0.0):+.6f}% <= 0%"
            )
    return reasons


def posthoc_sleeve_watchlist(
    aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    watchlist: list[dict[str, Any]] = []
    for component in COMPONENTS:
        item = aggregate.get("direction_attribution", {}).get(component, {})
        positive_folds = sum(
            int(result.get("direction_attribution", {}).get(component, {}).get("accepted_positions", 0)) >= 10
            and float(result.get("direction_attribution", {}).get(component, {}).get("return_contribution_pct", 0.0)) > 0
            for result in folds.values()
        )
        if (
            int(item.get("accepted_positions", 0)) >= 40
            and float(item.get("return_contribution_pct", 0.0)) > 0
            and positive_folds >= 2
        ):
            watchlist.append(
                {
                    "component_id": component,
                    "accepted_positions": int(item["accepted_positions"]),
                    "return_contribution_pct": float(item["return_contribution_pct"]),
                    "positive_fold_count": positive_folds,
                    "status": "posthoc_funding_sleeve_weak_feature_watchlist",
                    "allowed_as_standalone": False,
                }
            )
    return watchlist


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
            "regime_attribution",
        )
    }


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
    standalone: dict[str, Any] = {}
    for component in COMPONENTS:
        selected = [event for event in events if event["component_id"] == component]
        selected_aggregate = run_portfolio(selected, price_maps)
        selected_folds = {
            name: run_portfolio(fold_events(selected, start, end), price_maps)
            for name, start, end in LATE_FOLDS
        }
        standalone[component] = {
            "aggregate": summarize_result(selected_aggregate),
            "folds": {name: summarize_result(result) for name, result in selected_folds.items()},
            "positive_fold_count": sum(float(result["total_return_pct"]) > 0 for result in selected_folds.values()),
            "status": "posthoc_weak_feature_diagnostic_not_candidate",
        }
    return {
        "report_type": "funding_term_price_alignment_audit",
        "report_date": "2026-07-14",
        "research_id": BASE_COMPONENT,
        "scope": "observed_constant_universe_regime_conditioned_audit",
        "window": {"start": PRIMARY_START, "end": DATA_END},
        "constant_symbols": symbols,
        "aggregate": summarize_result(aggregate),
        "folds": {name: summarize_result(result) for name, result in folds.items()},
        "positive_fold_count": sum(float(result["total_return_pct"]) > 0 for result in folds.values()),
        "candidate_reasons": reasons,
        "status": "frozen_prospective_candidate" if not reasons else "observed_rejected",
        "posthoc_sleeve_weak_feature_watchlist": sleeve_watchlist,
        "posthoc_standalone_diagnostics": standalone,
        "prospective_validation_required": not reasons,
        "methodology_notes": [
            "This is a one-leg directional study, not the rejected four-leg funding carry trade.",
            "Only settled funding and completed price/regime inputs are used.",
            "All observations stop at 2026-07-10; prospective outcomes are not read.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines = [
        "# Funding-Term Price Alignment Audit",
        "",
        "Date: 2026-07-14",
        "",
        "Frozen one-leg directional audit. This is not four-leg carry.",
        "",
        "## Aggregate",
        "",
        f"- accepted positions: {aggregate['accepted_positions']}",
        f"- net return: {aggregate['total_return_pct']:+.6f}%",
        f"- maximum drawdown: {aggregate['max_drawdown_pct']:.6f}%",
        f"- win rate: {aggregate['realized_win_rate']:.2%}",
        f"- positive folds: {report['positive_fold_count']}/3",
        f"- top positive month share: {aggregate['top_positive_month_share']:.2%}",
        f"- status: `{report['status']}`",
        "",
        "## Direction Attribution",
        "",
        "| Sleeve | Accepted | Return Contribution | Win |",
        "| --- | ---: | ---: | ---: |",
    ]
    for component, item in aggregate["direction_attribution"].items():
        lines.append(
            f"| `{component}` | {item['accepted_positions']} | {item['return_contribution_pct']:+.6f}% | "
            f"{item['realized_win_rate']:.2%} |"
        )
    lines.extend(["", "## Regime Attribution", ""])
    for regime, item in aggregate["regime_attribution"].items():
        lines.append(
            f"- `{regime}`: {item['accepted_positions']} accepted, "
            f"{item['return_contribution_pct']:+.6f}% contribution, {item['realized_win_rate']:.2%} win"
        )
    lines.extend(["", "## Fold Returns", ""])
    for name, item in report["folds"].items():
        lines.append(f"- `{name}`: {item['total_return_pct']:+.6f}%")
    lines.extend(["", "## Decision Reasons", ""])
    if report["candidate_reasons"]:
        lines.extend(f"- {reason}" for reason in report["candidate_reasons"])
    else:
        lines.append("- Frozen observed screen passed; prospective validation remains mandatory.")
    if report["posthoc_sleeve_weak_feature_watchlist"]:
        lines.extend(["", "## Post-Hoc Sleeve Diagnostics", ""])
        for item in report["posthoc_sleeve_weak_feature_watchlist"]:
            diagnostic = report["posthoc_standalone_diagnostics"][item["component_id"]]
            result = diagnostic["aggregate"]
            lines.append(
                f"- `{item['component_id']}`: {result['accepted_positions']} accepted, "
                f"{result['total_return_pct']:+.6f}% return, {result['max_drawdown_pct']:.6f}% max DD, "
                f"{diagnostic['positive_fold_count']}/3 positive folds; standalone use prohibited."
            )
    lines.extend(
        [
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
    parser = argparse.ArgumentParser(description="Audit frozen funding-term price alignment.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/funding_term_price_alignment_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/funding_term_price_alignment_audit_2026-07-14.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), load_json(args.universe), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    aggregate = report["aggregate"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"accepted={aggregate['accepted_positions']}, return={aggregate['total_return_pct']:+.6f}%, "
        f"dd={aggregate['max_drawdown_pct']:.6f}%, folds={report['positive_fold_count']}/3, "
        f"status={report['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
