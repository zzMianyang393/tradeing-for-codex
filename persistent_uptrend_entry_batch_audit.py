"""Observed-data audit for three frozen persistent-uptrend entry hypotheses."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME
from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from market import Bar, FeatureBar, add_features, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import (
    DATA_END,
    DATA_START,
    DAY_MS,
    FOLDS,
    eligible_symbols,
    first_future_4h_exit,
    load_json,
    parse_day,
    trade_event,
)
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry
from uptrend_regime_structure_audit import walk_forward_fold


EMA_RECLAIM = "persistent_uptrend_ema20_reclaim"
BREAKOUT_20 = "persistent_uptrend_20bar_breakout"
DAILY_PULLBACK = "daily_ma_pullback_reclaim"
COMPONENTS = (EMA_RECLAIM, BREAKOUT_20, DAILY_PULLBACK)
INITIAL_EQUITY = 100_000.0
POSITION_FRACTION = 0.10
MAX_POSITIONS = 5


def run_ages(labels: list[tuple[int, str]]) -> list[int]:
    ages: list[int] = []
    current = 0
    for _ts, label in labels:
        current = current + 1 if label == LONG_COMPATIBLE_REGIME else 0
        ages.append(current)
    return ages


def persistent_context(local_label: str, local_age: int, btc_label: str) -> bool:
    return local_label == LONG_COMPATIBLE_REGIME and local_age > 60 and btc_label == LONG_COMPATIBLE_REGIME


def generate_4h_events(
    symbol: str,
    bars_15m: list[Bar],
    btc_labels: list[tuple[int, str]],
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    featured = add_features(resample_minutes(bars_15m, 240))
    labels = label_completed_4h_bars(bars_15m)
    ages = run_ages(labels)
    events: list[dict[str, Any]] = []
    next_available = {EMA_RECLAIM: 0, BREAKOUT_20: 0}

    for index in range(20, len(featured)):
        signal_ts = featured[index].ts + FOUR_HOURS_MS
        if not start_ts <= signal_ts <= end_ts:
            continue
        local_label = labels[index][1]
        btc_label = regime_at_entry(btc_labels, signal_ts)
        if not persistent_context(local_label, ages[index], btc_label):
            continue
        current = featured[index]
        previous = featured[index - 1]
        specifications: list[str] = []
        if previous.close <= previous.ema20 and current.close > current.ema20:
            specifications.append(EMA_RECLAIM)
        prior_high = max(bar.high for bar in featured[index - 20:index])
        if current.close > prior_high:
            specifications.append(BREAKOUT_20)

        for component in specifications:
            if signal_ts < next_available[component]:
                continue
            exit_ts = first_future_4h_exit(featured, index, lambda bar, _j: bar.close < bar.ema20)
            event = trade_event(
                symbol,
                component,
                "long",
                signal_ts,
                bars_15m,
                float(current.atr),
                exit_ts,
                10 * DAY_MS,
                end_ts,
                local_label,
            )
            if event is not None:
                event["uptrend_run_age_4h_bars"] = ages[index]
                event["btc_entry_regime"] = btc_label
                events.append(event)
                next_available[component] = int(event["exit_ts"]) + 15 * 60 * 1000
    return events


def first_future_daily_exit(featured: list[FeatureBar], start_index: int) -> int | None:
    for index in range(start_index + 1, len(featured)):
        if featured[index].close < featured[index].ema50:
            return featured[index].ts + DAY_MS
    return None


def generate_daily_events(
    symbol: str,
    bars_15m: list[Bar],
    local_labels: list[tuple[int, str]],
    btc_labels: list[tuple[int, str]],
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    featured = add_features(resample_minutes(bars_15m, 1440))
    events: list[dict[str, Any]] = []
    next_available = 0
    for index in range(1, len(featured)):
        signal_ts = featured[index].ts + DAY_MS
        if not start_ts <= signal_ts <= end_ts or signal_ts < next_available:
            continue
        current = featured[index]
        previous = featured[index - 1]
        local_label = regime_at_entry(local_labels, signal_ts)
        btc_label = regime_at_entry(btc_labels, signal_ts)
        if local_label != LONG_COMPATIBLE_REGIME or btc_label != LONG_COMPATIBLE_REGIME:
            continue
        if not (current.ema50 > current.ema200 and previous.close <= previous.ema20 and current.close > current.ema20):
            continue
        event = trade_event(
            symbol,
            DAILY_PULLBACK,
            "long",
            signal_ts,
            bars_15m,
            float(current.atr),
            first_future_daily_exit(featured, index),
            20 * DAY_MS,
            end_ts,
            local_label,
        )
        if event is not None:
            event["btc_entry_regime"] = btc_label
            events.append(event)
            next_available = int(event["exit_ts"]) + 15 * 60 * 1000
    return events


def generate_events(data_dir: Path, symbols: list[str]) -> tuple[list[dict[str, Any]], dict[str, dict[int, Bar]]]:
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
    loaded: dict[str, list[Bar]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        loaded[symbol] = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
    btc_symbol = next(symbol for symbol in symbols if symbol.startswith("BTC-"))
    btc_labels = label_completed_4h_bars(loaded[btc_symbol])
    events: list[dict[str, Any]] = []
    price_maps: dict[str, dict[int, Bar]] = {}
    for symbol, bars in loaded.items():
        local_labels = label_completed_4h_bars(bars)
        events.extend(generate_4h_events(symbol, bars, btc_labels, start_ts, end_ts))
        events.extend(generate_daily_events(symbol, bars, local_labels, btc_labels, start_ts, end_ts))
        price_maps[symbol] = {bar.ts: bar for bar in resample_minutes(bars, 1440)}
    return events, price_maps


def fold_events(events: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    start_ts = parse_day(start)
    end_ts = parse_day(end, end=True)
    return [
        event for event in events
        if start_ts <= int(event["entry_ts"]) <= end_ts and int(event["exit_ts"]) <= end_ts
    ]


def run_portfolio(events: list[dict[str, Any]], price_maps: dict[str, dict[int, Bar]]) -> dict[str, Any]:
    return simulate_portfolio(
        events,
        price_maps,
        initial_capital=INITIAL_EQUITY,
        max_positions=MAX_POSITIONS,
        position_fraction=POSITION_FRACTION,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
    )


def screen_reasons(aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if int(aggregate.get("accepted_positions", 0)) < 30:
        reasons.append(f"accepted positions {aggregate.get('accepted_positions', 0)} < 30")
    if float(aggregate.get("total_return_pct", 0.0)) <= 0:
        reasons.append(f"aggregate return {aggregate.get('total_return_pct', 0.0):+.6f}% <= 0%")
    if float(aggregate.get("max_drawdown_pct", 0.0)) > 20.0:
        reasons.append(f"maximum drawdown {aggregate['max_drawdown_pct']:.6f}% > 20%")
    positive_folds = sum(float(item.get("total_return_pct", 0.0)) > 0 for item in folds.values())
    if positive_folds < 3:
        reasons.append(f"positive folds {positive_folds}/5 < 3/5")
    concentration = float(aggregate.get("top_positive_month_share", 0.0))
    if concentration > 0.25:
        reasons.append(f"top positive month share {concentration:.2%} > 25%")
    return reasons


def classify_panel(aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]) -> str:
    positive_folds = sum(float(item.get("total_return_pct", 0.0)) > 0 for item in folds.values())
    core_pass = (
        int(aggregate.get("accepted_positions", 0)) >= 30
        and float(aggregate.get("total_return_pct", 0.0)) > 0
        and float(aggregate.get("max_drawdown_pct", 0.0)) <= 20.0
        and positive_folds >= 3
    )
    if not core_pass:
        return "observed_rejected"
    if float(aggregate.get("top_positive_month_share", 0.0)) > 0.25:
        return "weak_feature_watchlist_concentration_penalty"
    return "observed_candidate"


def panel_summary(events: list[dict[str, Any]], price_maps: dict[str, dict[int, Bar]]) -> dict[str, Any]:
    aggregate = run_portfolio(events, price_maps)
    folds = {
        name: run_portfolio(fold_events(events, start, end), price_maps)
        for name, start, end in FOLDS
    }
    reasons = screen_reasons(aggregate, folds)
    status = classify_panel(aggregate, folds)
    return {
        "generated_events": len(events),
        "aggregate": aggregate,
        "folds": folds,
        "positive_fold_count": sum(float(item["total_return_pct"]) > 0 for item in folds.values()),
        "screen_reasons": reasons,
        "status": status,
        "eligible_as_directional_weak_feature": status in {
            "observed_candidate",
            "weak_feature_watchlist_concentration_penalty",
        },
        "allowed_as_standalone": False,
    }


def expanding_panel_events(events: list[dict[str, Any]], universe: dict[str, Any]) -> list[dict[str, Any]]:
    eligible = {
        fold: set(symbols) for fold, symbols in universe["eligible_symbols_by_fold"].items()
    }
    return [
        event for event in events
        if str(event["symbol"]) in eligible.get(walk_forward_fold(int(event["entry_ts"])), set())
    ]


def build_report(coverage: dict[str, Any], universe: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    all_events, price_maps = generate_events(data_dir, symbols)
    primary_symbols = set(str(symbol) for symbol in universe["constant_full_window_symbols"])
    components: dict[str, Any] = {}
    for component in COMPONENTS:
        component_events = [event for event in all_events if event["component_id"] == component]
        primary = [event for event in component_events if str(event["symbol"]) in primary_symbols]
        secondary = expanding_panel_events(component_events, universe)
        primary_summary = panel_summary(primary, price_maps)
        components[component] = {
            "direction_counts": dict(Counter(str(event["direction"]) for event in component_events)),
            "primary_constant_universe": primary_summary,
            "secondary_fold_eligible_universe": panel_summary(secondary, price_maps),
            "status": primary_summary["status"],
            "prospective_required_if_passed": primary_summary["status"] == "observed_candidate",
            "combo_concentration_penalty_required": primary_summary["status"] == "weak_feature_watchlist_concentration_penalty",
        }
    return {
        "report_type": "persistent_uptrend_entry_batch_audit",
        "report_date": "2026-07-13",
        "scope": "posthoc_observed_data_diagnostic_not_unseen_validation",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "primary_constant_universe_symbols": sorted(primary_symbols),
        "secondary_universe_contract": "98pct_fold_eligible_symbols",
        "position_fraction": POSITION_FRACTION,
        "max_positions": MAX_POSITIONS,
        "components": components,
        "candidate_components": [name for name, item in components.items() if item["status"] == "observed_candidate"],
        "weak_feature_watchlist": [
            name for name, item in components.items()
            if item["status"] == "weak_feature_watchlist_concentration_penalty"
        ],
        "methodology_notes": [
            "The greater-than-10-day persistence condition is post-hoc discovery from the preceding structure audit.",
            "The primary constant-universe panel controls symbol-universe drift.",
            "The secondary expanding panel cannot rescue a failed primary panel.",
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
    lines = [
        "# Persistent Uptrend Entry Batch Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Post-hoc observed-data diagnostic. The constant BTC/ETH universe is the primary panel.",
        "",
        "## Primary Constant-Universe Results",
        "",
        "| Component | Accepted | Return | Max DD | Positive Folds | Month Concentration | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, item in report["components"].items():
        panel = item["primary_constant_universe"]
        result = panel["aggregate"]
        lines.append(
            f"| `{name}` | {result['accepted_positions']} | {result['total_return_pct']:+.6f}% | "
            f"{result['max_drawdown_pct']:.6f}% | {panel['positive_fold_count']}/5 | "
            f"{result['top_positive_month_share']:.2%} | `{panel['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Secondary Fold-Eligible Results",
            "",
            "| Component | Accepted | Return | Max DD | Positive Folds | Status |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for name, item in report["components"].items():
        panel = item["secondary_fold_eligible_universe"]
        result = panel["aggregate"]
        lines.append(
            f"| `{name}` | {result['accepted_positions']} | {result['total_return_pct']:+.6f}% | "
            f"{result['max_drawdown_pct']:.6f}% | {panel['positive_fold_count']}/5 | `{panel['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Primary Fold Returns",
            "",
            "| Component | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, item in report["components"].items():
        fold_values = " | ".join(
            f"{item['primary_constant_universe']['folds'][fold_name]['total_return_pct']:+.6f}%"
            for fold_name, _start, _end in FOLDS
        )
        lines.append(f"| `{name}` | {fold_values} |")
    lines.extend(["", "## Primary Decisions", ""])
    for name, item in report["components"].items():
        reasons = item["primary_constant_universe"]["screen_reasons"]
        if item["status"] == "weak_feature_watchlist_concentration_penalty":
            decision = "retain only as a directional weak-feature watchlist item with a concentration penalty; standalone use prohibited"
        elif not reasons:
            decision = "passed observed screen; prospective validation required"
        else:
            decision = "; ".join(reasons)
        lines.append(f"- `{name}`: {decision}")
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
    parser = argparse.ArgumentParser(description="Audit frozen persistent-uptrend entry hypotheses.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/persistent_uptrend_entry_batch_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/persistent_uptrend_entry_batch_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), load_json(args.universe), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    for name, item in report["components"].items():
        result = item["primary_constant_universe"]["aggregate"]
        print(
            f"{name}: accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
            f"dd={result['max_drawdown_pct']:.6f}%, status={item['status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
