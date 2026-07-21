"""Recheck frozen range components inside the post-hoc efficiency-ratio label."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import (
    BB_COMPONENT,
    DATA_END,
    DATA_START,
    FOLDS,
    RSI_COMPONENT,
    candidate_reasons,
    eligible_symbols,
    fold_events,
    generate_4h_events,
    load_json,
    parse_day,
    run_portfolio,
)
from regime_validation_v2 import LOW_VOLATILITY_DRIFT, MEAN_REVERTING_RANGE, label_completed_4h_bars_v2


COMPONENTS = (BB_COMPONENT, RSI_COMPONENT)


def generate_v2_events(
    data_dir: Path,
    symbols: list[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[int, Bar]], dict[str, int]]:
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
    events: list[dict[str, Any]] = []
    price_maps: dict[str, dict[int, Bar]] = {}
    label_counts = {MEAN_REVERTING_RANGE: 0, LOW_VOLATILITY_DRIFT: 0}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        labels = label_completed_4h_bars_v2(bars)
        for available_ts, label in labels:
            if start_ts <= available_ts <= end_ts and label in label_counts:
                label_counts[label] += 1
        generated = generate_4h_events(
            symbol,
            bars,
            labels,
            start_ts,
            end_ts,
            range_regimes={MEAN_REVERTING_RANGE},
        )
        events.extend(event for event in generated if event["component_id"] in COMPONENTS)
        price_maps[symbol] = {bar.ts: bar for bar in resample_minutes(bars, 1440)}
    return events, price_maps, label_counts


def build_report(coverage: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    events, price_maps, label_counts = generate_v2_events(data_dir, symbols)
    components: dict[str, Any] = {}
    for component in COMPONENTS:
        candidates = [event for event in events if event["component_id"] == component]
        aggregate = run_portfolio(candidates, price_maps)
        folds = {
            name: run_portfolio(fold_events(candidates, start, end), price_maps)
            for name, start, end in FOLDS
        }
        reasons = candidate_reasons(aggregate, folds)
        components[component] = {
            "generated_events": len(candidates),
            "aggregate": aggregate,
            "folds": folds,
            "positive_fold_count": sum(float(item["total_return_pct"]) > 0 for item in folds.values()),
            "candidate_reasons": reasons,
            "status": "posthoc_historical_candidate" if not reasons else "posthoc_historical_rejected",
        }
    return {
        "report_type": "range_regime_v2_walk_forward_audit",
        "report_date": "2026-07-13",
        "scope": "posthoc_label_refinement_on_observed_data",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "label_definition": {
            "lookback_4h_bars": 6,
            "efficiency_ratio_max": 0.30,
            "mean_reverting_label": MEAN_REVERTING_RANGE,
            "drift_label": LOW_VOLATILITY_DRIFT,
        },
        "label_counts": label_counts,
        "eligible_symbols": symbols,
        "components": components,
        "candidate_components": [name for name, item in components.items() if not item["candidate_reasons"]],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["label_counts"]
    total = sum(counts.values())
    lines = [
        "# Mean-Reverting Range V2 Walk-Forward Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Post-hoc label refinement on observed data; prospective validation remains mandatory.",
        "",
        "## Label Split",
        "",
        f"- `{MEAN_REVERTING_RANGE}`: {counts[MEAN_REVERTING_RANGE]} ({counts[MEAN_REVERTING_RANGE] / total:.2%})",
        f"- `{LOW_VOLATILITY_DRIFT}`: {counts[LOW_VOLATILITY_DRIFT]} ({counts[LOW_VOLATILITY_DRIFT] / total:.2%})",
        "",
        "## Results",
        "",
        "| Component | Events | Accepted | Return | Max DD | Win | Positive Folds | Month Concentration | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, item in report["components"].items():
        result = item["aggregate"]
        lines.append(
            f"| `{name}` | {item['generated_events']} | {result['accepted_positions']} | "
            f"{result['total_return_pct']:+.6f}% | {result['max_drawdown_pct']:.6f}% | "
            f"{result['realized_win_rate']:.2%} | {item['positive_fold_count']}/5 | "
            f"{result['top_positive_month_share']:.2%} | `{item['status']}` |"
        )
    lines.extend(["", "## Fold Returns", "", "| Component | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for name, item in report["components"].items():
        values = " | ".join(f"{item['folds'][fold[0]]['total_return_pct']:+.6f}%" for fold in FOLDS)
        lines.append(f"| `{name}` | {values} |")
    lines.extend(["", "## Safety", "", "- `approved_for_paper = []`", "- `eligible_for_paper = false`", "- `safe_to_enable_trading = false`", "- `ready_for_combo_backtest = false`", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recheck frozen range components under the v2 label.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/range_regime_v2_walk_forward_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/range_regime_v2_walk_forward_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    for name, item in report["components"].items():
        result = item["aggregate"]
        print(
            f"{name}: accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
            f"max_dd={result['max_drawdown_pct']:.6f}%, folds={item['positive_fold_count']}/5, status={item['status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

