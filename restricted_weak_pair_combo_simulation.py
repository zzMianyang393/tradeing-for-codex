"""Shared-capital simulations for weak-component pairs that passed complementarity gates."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from low_volatility_drift_fixed_risk_audit import load_price_maps
from regime_component_walk_forward_audit import DATA_END, DATA_START, FOLDS, eligible_symbols, load_json
from persistent_uptrend_entry_batch_audit import fold_events
from two_regime_shared_capital_combo_simulation import component_attribution
from weak_component_complementarity_audit import component_events


POSITION_FRACTION = 0.10
MAX_POSITIONS = 5


def run_shared(
    events: list[dict[str, Any]],
    price_maps: dict[str, dict[int, Any]],
    components: tuple[str, str],
) -> dict[str, Any]:
    result = simulate_portfolio(
        events,
        price_maps,
        initial_capital=100_000.0,
        max_positions=MAX_POSITIONS,
        position_fraction=POSITION_FRACTION,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
    )
    result["component_attribution"] = component_attribution(result, components)
    return result


def combo_reasons(
    aggregate: dict[str, Any],
    folds: dict[str, dict[str, Any]],
    standalone: dict[str, dict[str, Any]],
    components: tuple[str, str],
) -> list[str]:
    reasons: list[str] = []
    if int(aggregate.get("accepted_positions", 0)) < 50:
        reasons.append(f"accepted positions {aggregate.get('accepted_positions', 0)} < 50")
    if float(aggregate.get("total_return_pct", 0.0)) <= 0:
        reasons.append(f"aggregate return {aggregate.get('total_return_pct', 0.0):+.6f}% <= 0%")
    drawdown_limit = max(float(standalone[name]["max_drawdown_pct"]) for name in components)
    if float(aggregate.get("max_drawdown_pct", 0.0)) > drawdown_limit:
        reasons.append(
            f"maximum drawdown {aggregate['max_drawdown_pct']:.6f}% > worse standalone {drawdown_limit:.6f}%"
        )
    positive_folds = sum(float(item.get("total_return_pct", 0.0)) > 0 for item in folds.values())
    if positive_folds < 3:
        reasons.append(f"positive folds {positive_folds}/5 < 3/5")
    if float(aggregate.get("top_positive_month_share", 0.0)) > 0.25:
        reasons.append(f"top positive month share {aggregate['top_positive_month_share']:.2%} > 25%")
    attribution = aggregate.get("component_attribution", {})
    for component in components:
        item = attribution.get(component, {})
        if int(item.get("accepted_positions", 0)) < 10:
            reasons.append(f"{component} accepted positions {item.get('accepted_positions', 0)} < 10")
        if float(item.get("return_contribution_pct", 0.0)) <= 0:
            reasons.append(
                f"{component} return contribution {item.get('return_contribution_pct', 0.0):+.6f}% <= 0%"
            )
    return reasons


def posthoc_risk_adjusted_watchlist(
    aggregate: dict[str, Any],
    reasons: list[str],
    standalone: dict[str, dict[str, Any]],
    components: tuple[str, str],
    positive_folds: int,
) -> dict[str, Any]:
    worse_standalone_dd = max(float(standalone[name]["max_drawdown_pct"]) for name in components)
    dd = float(aggregate.get("max_drawdown_pct", 0.0))
    relative_excess = (dd / worse_standalone_dd - 1.0) if worse_standalone_dd > 0 else 0.0
    return_to_dd = float(aggregate.get("total_return_pct", 0.0)) / dd if dd > 0 else 0.0
    contributions = aggregate.get("component_attribution", {})
    only_drawdown_failure = bool(reasons) and all(reason.startswith("maximum drawdown") for reason in reasons)
    retained = (
        only_drawdown_failure
        and relative_excess <= 0.10
        and positive_folds >= 4
        and float(aggregate.get("top_positive_month_share", 0.0)) <= 0.25
        and all(float(contributions.get(name, {}).get("return_contribution_pct", 0.0)) > 0 for name in components)
    )
    return {
        "retained_as_posthoc_risk_adjusted_watchlist": retained,
        "strict_gate_still_failed": bool(reasons),
        "worse_standalone_max_drawdown_pct": round(worse_standalone_dd, 6),
        "drawdown_excess_percentage_points": round(dd - worse_standalone_dd, 6),
        "relative_drawdown_excess": round(relative_excess, 6),
        "return_to_drawdown_ratio": round(return_to_dd, 6),
        "interpretation": "descriptive_posthoc_not_a_gate_override",
    }


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
            "component_attribution",
        )
    }


def build_report(
    complementarity: dict[str, Any],
    drift: dict[str, Any],
    uptrend: dict[str, Any],
    coverage: dict[str, Any],
    universe: dict[str, Any],
    data_dir: Path,
) -> dict[str, Any]:
    allowed_pair_ids = list(complementarity.get("restricted_combo_pairs", []))
    events_by_component = component_events(drift, uptrend, coverage, universe, data_dir)
    price_maps = load_price_maps(data_dir, eligible_symbols(coverage))
    standalone = complementarity.get("components", {})
    pairs: dict[str, Any] = {}
    passing: list[str] = []
    for pair_id in allowed_pair_ids:
        left, right = pair_id.split("__", 1)
        components = (left, right)
        events = events_by_component[left] + events_by_component[right]
        aggregate = run_shared(events, price_maps, components)
        fold_results = {
            name: run_shared(fold_events(events, start, end), price_maps, components)
            for name, start, end in FOLDS
        }
        reasons = combo_reasons(aggregate, fold_results, standalone, components)
        positive_folds = sum(float(result["total_return_pct"]) > 0 for result in fold_results.values())
        secondary = posthoc_risk_adjusted_watchlist(
            aggregate, reasons, standalone, components, positive_folds
        )
        pairs[pair_id] = {
            "components": list(components),
            "component_candidate_counts": dict(Counter(str(event["component_id"]) for event in events)),
            "aggregate": summarize_result(aggregate),
            "folds": {name: summarize_result(result) for name, result in fold_results.items()},
            "positive_fold_count": positive_folds,
            "diagnostic_reasons": reasons,
            "status": "frozen_observed_combo_candidate" if not reasons else "observed_combo_rejected",
            "prospective_joint_observation_required": not reasons,
            "posthoc_risk_adjusted_interpretation": secondary,
        }
        if not reasons:
            passing.append(pair_id)
    return {
        "report_type": "restricted_weak_pair_combo_simulation",
        "report_date": "2026-07-13",
        "scope": "posthoc_observed_shared_capital_diagnostic",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "portfolio_rules": {
            "initial_capital": 100_000.0,
            "position_fraction": POSITION_FRACTION,
            "max_positions": MAX_POSITIONS,
            "one_position_per_symbol": True,
            "component_reservation": False,
            "leverage": 1.0,
        },
        "source_restricted_pairs": allowed_pair_ids,
        "pairs": pairs,
        "frozen_observed_combo_candidates": passing,
        "posthoc_risk_adjusted_combo_watchlist": [
            pair_id for pair_id, item in pairs.items()
            if item["posthoc_risk_adjusted_interpretation"]["retained_as_posthoc_risk_adjusted_watchlist"]
        ],
        "methodology_notes": [
            "Only pairs admitted by the frozen complementarity audit are simulated.",
            "Underlying component events and costs are unchanged.",
            "A passing result remains post-hoc and requires joint prospective observation.",
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
        "# Restricted Weak-Pair Combo Simulation",
        "",
        "Date: 2026-07-13",
        "",
        "Post-hoc shared-capital diagnostic. Only complementarity-approved pairs are included.",
        "",
        "## Aggregate Results",
        "",
        "| Pair | Accepted | Return | Max DD | DD Excess | Return/DD | Positive Folds | Month Concentration | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for pair_id, item in report["pairs"].items():
        result = item["aggregate"]
        secondary = item["posthoc_risk_adjusted_interpretation"]
        lines.append(
            f"| `{pair_id}` | {result['accepted_positions']} | {result['total_return_pct']:+.6f}% | "
            f"{result['max_drawdown_pct']:.6f}% | {secondary['drawdown_excess_percentage_points']:+.6f}pp | "
            f"{secondary['return_to_drawdown_ratio']:.4f} | "
            f"{item['positive_fold_count']}/5 | {result['top_positive_month_share']:.2%} | `{item['status']}` |"
        )
    lines.extend(
        [
            "",
            "## Fold Returns",
            "",
            "| Pair | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for pair_id, item in report["pairs"].items():
        values = " | ".join(
            f"{item['folds'][name]['total_return_pct']:+.6f}%" for name, _start, _end in FOLDS
        )
        lines.append(f"| `{pair_id}` | {values} |")
    lines.extend(["", "## Component Attribution", ""])
    for pair_id, item in report["pairs"].items():
        lines.extend(
            [
                f"### `{pair_id}`",
                "",
                "| Component | Accepted | Rejected | Return Contribution | Win |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for component, attribution in item["aggregate"]["component_attribution"].items():
            lines.append(
                f"| `{component}` | {attribution['accepted_positions']} | {attribution['rejected_events']} | "
                f"{attribution['return_contribution_pct']:+.6f}% | {attribution['realized_win_rate']:.2%} |"
            )
        lines.append("")
    lines.extend(["## Decisions", ""])
    for pair_id, item in report["pairs"].items():
        decision = (
            "freeze unchanged for joint prospective observation"
            if not item["diagnostic_reasons"]
            else "; ".join(item["diagnostic_reasons"])
        )
        lines.append(f"- `{pair_id}`: {decision}")
        if item["posthoc_risk_adjusted_interpretation"]["retained_as_posthoc_risk_adjusted_watchlist"]:
            lines.append(
                "  Post-hoc interpretation: retain as a risk-adjusted combo watchlist item; "
                "this does not override the failed pre-registered drawdown gate."
            )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- no paper or production gate is opened",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate complementarity-approved weak-component pairs.")
    parser.add_argument("--complementarity", type=Path, default=Path("reports/weak_component_complementarity_audit.json"))
    parser.add_argument("--drift", type=Path, default=Path("reports/low_volatility_drift_fixed_risk_audit.json"))
    parser.add_argument("--uptrend", type=Path, default=Path("reports/persistent_uptrend_entry_batch_audit.json"))
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/restricted_weak_pair_combo_simulation.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/restricted_weak_pair_combo_simulation_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(
        load_json(args.complementarity),
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
    for pair_id, item in report["pairs"].items():
        result = item["aggregate"]
        print(
            f"{pair_id}: accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
            f"dd={result['max_drawdown_pct']:.6f}%, folds={item['positive_fold_count']}/5, status={item['status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
