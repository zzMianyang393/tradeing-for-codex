"""Complementarity audit for the post-hoc range microtrend long sleeve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from daily_volume_shock_reversal_audit import (
    PRIMARY_START,
    SHORT_COMPONENT as VOLUME_SHORT,
    generate_symbol_events,
    late_constant_symbols,
)
from low_volatility_drift_fixed_risk_audit import load_price_maps
from market import load_quantify_15m_csv
from regime_component_walk_forward_audit import DATA_END, eligible_symbols, load_json, parse_day
from volume_shock_short_complementarity_audit import filter_common_window, run_component
from weak_component_complementarity_audit import (
    COMPONENTS as EXISTING_COMPONENTS,
    active_days,
    component_events,
    equity_daily_returns,
    event_interval_overlap,
    jaccard,
    monthly_returns,
    overlap_coefficient,
    pair_reasons,
    pearson,
    summarize_result,
)
from weekly_range_microtrend_continuation_audit import (
    LONG_COMPONENT as RANGE_LONG,
    generate_events as generate_range_events,
)
from weekly_weakest_short_complementarity_audit import duplication_diagnosis


COMPARISON_COMPONENTS = (*EXISTING_COMPONENTS, VOLUME_SHORT)


def build_report(
    drift: dict[str, Any],
    uptrend: dict[str, Any],
    coverage: dict[str, Any],
    universe: dict[str, Any],
    data_dir: Path,
) -> dict[str, Any]:
    symbols = set(late_constant_symbols(universe))
    start_ts = parse_day(PRIMARY_START)
    end_ts = parse_day(DATA_END, end=True)
    existing = component_events(drift, uptrend, coverage, universe, data_dir)
    events_by_component = {
        component: filter_common_window(events, symbols, start_ts, end_ts)
        for component, events in existing.items()
    }
    volume_events: list[dict[str, Any]] = []
    for symbol in sorted(symbols):
        base = symbol.split("-", 1)[0]
        generated = generate_symbol_events(
            symbol,
            load_quantify_15m_csv(data_dir / f"{base}_15m.csv"),
            start_ts,
            end_ts,
        )
        volume_events.extend(event for event in generated if event["component_id"] == VOLUME_SHORT)
    events_by_component[VOLUME_SHORT] = volume_events
    events_by_component[RANGE_LONG] = [
        event
        for event in generate_range_events(data_dir, sorted(symbols), start_ts, end_ts)
        if event["component_id"] == RANGE_LONG
    ]

    price_maps = load_price_maps(data_dir, eligible_symbols(coverage))
    simulations = {
        component: run_component(events, price_maps)
        for component, events in events_by_component.items()
    }
    daily = {
        component: equity_daily_returns(result, start_ts, end_ts)
        for component, result in simulations.items()
    }
    monthly = {component: monthly_returns(values) for component, values in daily.items()}
    active = {
        component: active_days(result.get("closed_positions", []))
        for component, result in simulations.items()
    }
    pairs: dict[str, Any] = {}
    retained: list[str] = []
    for comparison in COMPARISON_COMPONENTS:
        active_union = sorted(active[RANGE_LONG] | active[comparison])
        common_months = sorted(set(monthly[RANGE_LONG]) | set(monthly[comparison]))
        negative_range = {day for day, value in daily[RANGE_LONG].items() if value < 0}
        negative_comparison = {day for day, value in daily[comparison].items() if value < 0}
        metrics = {
            "active_union_daily_return_correlation": pearson(
                [daily[RANGE_LONG].get(day, 0.0) for day in active_union],
                [daily[comparison].get(day, 0.0) for day in active_union],
            ),
            "monthly_return_correlation": pearson(
                [monthly[RANGE_LONG].get(month, 0.0) for month in common_months],
                [monthly[comparison].get(month, 0.0) for month in common_months],
            ),
            "active_day_jaccard": jaccard(active[RANGE_LONG], active[comparison]),
            "negative_day_overlap_coefficient": overlap_coefficient(negative_range, negative_comparison),
            "active_days_range": len(active[RANGE_LONG]),
            "active_days_comparison": len(active[comparison]),
            "negative_days_range": len(negative_range),
            "negative_days_comparison": len(negative_comparison),
            "event_overlap": event_interval_overlap(
                simulations[RANGE_LONG].get("closed_positions", []),
                simulations[comparison].get("closed_positions", []),
            ),
        }
        reasons = pair_reasons(simulations[RANGE_LONG], simulations[comparison], metrics)
        pair_id = f"{RANGE_LONG}__{comparison}"
        pairs[pair_id] = {
            "left": RANGE_LONG,
            "right": comparison,
            "metrics": metrics,
            "duplication_diagnosis": duplication_diagnosis(metrics),
            "watchlist_reasons": reasons,
            "retained_for_prospective_pair_comparison": not reasons,
            "eligible_for_restricted_combo_simulation": False,
            "combo_block_reason": "range microtrend long is post-hoc from a failed bidirectional rule",
        }
        if not reasons:
            retained.append(pair_id)
    return {
        "report_type": "range_microtrend_long_complementarity_audit",
        "report_date": "2026-07-14",
        "scope": "posthoc_regime_sleeve_common_window_complementarity",
        "common_window": {"start": PRIMARY_START, "end": DATA_END},
        "constant_symbols": sorted(symbols),
        "components": {name: summarize_result(result) for name, result in simulations.items()},
        "pairs": pairs,
        "retained_prospective_pair_watchlist": retained,
        "restricted_combo_simulation_authorized": False,
        "methodology_notes": [
            "All components are normalized on the same 2025+ constant-universe window.",
            "Economic duplication is separated from operational active-day overlap.",
            "The range-long sleeve is post-hoc and cannot authorize a combo simulation.",
            "No strategy rule, exit, cost, label, or allocation is changed.",
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
        "# Range Microtrend Long Complementarity Audit",
        "",
        "Date: 2026-07-14",
        "",
        "Post-hoc weak-feature diagnostic. No historical combo simulation is authorized.",
        "",
        "## Normalized Components",
        "",
        "| Component | Accepted | Return | Max DD | Win | Month Concentration |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, item in report["components"].items():
        lines.append(
            f"| `{name}` | {item['accepted_positions']} | {item['total_return_pct']:+.6f}% | "
            f"{item['max_drawdown_pct']:.6f}% | {item['realized_win_rate']:.2%} | "
            f"{item['top_positive_month_share']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Pair Metrics",
            "",
            "| Comparison | Daily Corr | Monthly Corr | Active Jaccard | Negative Overlap | Same-Symbol Overlaps | Diagnosis | Strict Pair |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for item in report["pairs"].values():
        metrics = item["metrics"]
        lines.append(
            f"| `{item['right']}` | {metrics['active_union_daily_return_correlation']:+.4f} | "
            f"{metrics['monthly_return_correlation']:+.4f} | {metrics['active_day_jaccard']:.2%} | "
            f"{metrics['negative_day_overlap_coefficient']:.2%} | "
            f"{metrics['event_overlap']['same_symbol_overlapping_pairs']} | "
            f"`{item['duplication_diagnosis']['interpretation']}` | "
            f"`{str(item['retained_for_prospective_pair_comparison']).lower()}` |"
        )
    lines.extend(["", "## Decisions", ""])
    for pair_id, item in report["pairs"].items():
        decision = "retain for prospective pair comparison only" if not item["watchlist_reasons"] else "; ".join(item["watchlist_reasons"])
        lines.append(f"- `{pair_id}`: {decision}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- restricted combo simulation authorized: `false`",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit range microtrend long complementarity.")
    parser.add_argument("--drift", type=Path, default=Path("reports/low_volatility_drift_fixed_risk_audit.json"))
    parser.add_argument("--uptrend", type=Path, default=Path("reports/persistent_uptrend_entry_batch_audit.json"))
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/range_microtrend_long_complementarity_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/range_microtrend_long_complementarity_audit_2026-07-14.md"))
    args = parser.parse_args(argv)
    report = build_report(
        load_json(args.drift),
        load_json(args.uptrend),
        load_json(args.coverage),
        load_json(args.universe),
        args.data,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(f"retained_pairs={report['retained_prospective_pair_watchlist']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
