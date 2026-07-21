"""Post-hoc historical screen for BB continuation inside low-volatility drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from market import Bar, FeatureBar, add_features, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import (
    DATA_END,
    DATA_START,
    FOLDS,
    candidate_reasons,
    eligible_symbols,
    first_future_4h_exit,
    fold_events,
    load_json,
    parse_day,
    run_portfolio,
    trade_event,
)
from regime_validation import FOUR_HOURS_MS, regime_at_entry
from regime_validation_v2 import LOW_VOLATILITY_DRIFT, label_completed_4h_bars_v2


COMPONENT = "low_volatility_drift_bb_breakout"


def breakout_direction(previous: FeatureBar, current: FeatureBar) -> str | None:
    if previous.close <= previous.bb_upper and current.close > current.bb_upper:
        return "long"
    if previous.close >= previous.bb_lower and current.close < current.bb_lower:
        return "short"
    return None


def generate_symbol_events(
    symbol: str,
    bars_15m: list[Bar],
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    raw_4h = resample_minutes(bars_15m, 240)
    featured = add_features(raw_4h)
    labels = label_completed_4h_bars_v2(bars_15m)
    events: list[dict[str, Any]] = []
    next_available = 0
    for index in range(1, len(featured)):
        signal_ts = featured[index].ts + FOUR_HOURS_MS
        if signal_ts < start_ts or signal_ts > end_ts or signal_ts < next_available:
            continue
        if regime_at_entry(labels, signal_ts) != LOW_VOLATILITY_DRIFT:
            continue
        direction = breakout_direction(featured[index - 1], featured[index])
        if direction is None:
            continue
        if direction == "long":
            exit_ts = first_future_4h_exit(featured, index, lambda bar, _j: bar.close <= bar.bb_mid)
        else:
            exit_ts = first_future_4h_exit(featured, index, lambda bar, _j: bar.close >= bar.bb_mid)
        event = trade_event(
            symbol,
            COMPONENT,
            direction,
            signal_ts,
            bars_15m,
            float(featured[index].atr),
            exit_ts,
            3 * 24 * 60 * 60 * 1000,
            end_ts,
            LOW_VOLATILITY_DRIFT,
        )
        if event is not None:
            events.append(event)
            next_available = int(event["exit_ts"]) + 15 * 60 * 1000
    return events


def build_report(coverage: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
    events: list[dict[str, Any]] = []
    price_maps: dict[str, dict[int, Bar]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        events.extend(generate_symbol_events(symbol, bars, start_ts, end_ts))
        price_maps[symbol] = {bar.ts: bar for bar in resample_minutes(bars, 1440)}

    aggregate = run_portfolio(events, price_maps)
    folds = {
        name: run_portfolio(fold_events(events, start, end), price_maps)
        for name, start, end in FOLDS
    }
    reasons = candidate_reasons(aggregate, folds)
    return {
        "report_type": "low_volatility_drift_breakout_audit",
        "report_date": "2026-07-13",
        "scope": "posthoc_historical_hypothesis_requires_prospective_validation",
        "component": COMPONENT,
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "eligible_symbols": symbols,
        "generated_events": len(events),
        "aggregate": aggregate,
        "folds": folds,
        "positive_fold_count": sum(float(item["total_return_pct"]) > 0 for item in folds.values()),
        "candidate_reasons": reasons,
        "status": "posthoc_prospective_candidate" if not reasons else "posthoc_historical_rejected",
        "prospective_validation_required": True,
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
        "# Low-Volatility Drift Breakout Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Post-hoc observed-data hypothesis; prospective validation is mandatory.",
        "",
        "## Aggregate",
        "",
        f"- generated events: {report['generated_events']}",
        f"- accepted positions: {result['accepted_positions']}",
        f"- return: {result['total_return_pct']:+.6f}%",
        f"- maximum drawdown: {result['max_drawdown_pct']:.6f}%",
        f"- win rate: {result['realized_win_rate']:.2%}",
        f"- positive half-year folds: {report['positive_fold_count']}/5",
        f"- top positive month share: {result['top_positive_month_share']:.2%}",
        "",
        "## Fold Returns",
        "",
        "| 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
        "| ---: | ---: | ---: | ---: | ---: |",
        "| " + " | ".join(f"{report['folds'][fold[0]]['total_return_pct']:+.6f}%" for fold in FOLDS) + " |",
        "",
        "## Decision",
        "",
    ]
    if report["candidate_reasons"]:
        lines.extend(f"- {reason}" for reason in report["candidate_reasons"])
    else:
        lines.append("- Passed the post-hoc historical screen; freeze for prospective observation only.")
    lines.extend(["", f"Status: `{report['status']}`.", "", "## Safety", "", "- `approved_for_paper = []`", "- `eligible_for_paper = false`", "- `safe_to_enable_trading = false`", "- `ready_for_combo_backtest = false`", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit BB continuation inside low-volatility drift.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/low_volatility_drift_breakout_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/low_volatility_drift_breakout_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    result = report["aggregate"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
        f"max_dd={result['max_drawdown_pct']:.6f}%, folds={report['positive_fold_count']}/5, status={report['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

