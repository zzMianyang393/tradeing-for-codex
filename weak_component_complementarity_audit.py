"""Audit return and event complementarity among three frozen weak components."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from downtrend_bidirectional_combo_simulation import EMA_COMPONENT
from downtrend_bidirectional_future_validation import generate_frozen_events
from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from low_volatility_drift_fixed_risk_audit import candidate_events_from_result, load_price_maps
from persistent_uptrend_entry_batch_audit import expanding_panel_events
from regime_component_walk_forward_audit import DATA_END, DATA_START, DAY_MS, eligible_symbols, load_json, parse_day


DRIFT = "low_volatility_drift_bb_breakout_fixed_risk_v1"
UPTREND = "persistent_uptrend_ema20_reclaim_v1"
DOWNTREND = "ema_continuation_short_downtrend_v1"
COMPONENTS = (DRIFT, UPTREND, DOWNTREND)
POSITION_FRACTION = 0.10
MAX_POSITIONS = 5


def pearson(values_a: list[float], values_b: list[float]) -> float:
    if len(values_a) != len(values_b):
        raise ValueError("series lengths must match")
    if len(values_a) < 2:
        return 0.0
    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    numerator = sum((a - mean_a) * (b - mean_b) for a, b in zip(values_a, values_b))
    denominator_a = math.sqrt(sum((a - mean_a) ** 2 for a in values_a))
    denominator_b = math.sqrt(sum((b - mean_b) ** 2 for b in values_b))
    if denominator_a == 0.0 or denominator_b == 0.0:
        return 0.0
    return round(numerator / (denominator_a * denominator_b), 6)


def equity_daily_returns(result: dict[str, Any], start_ts: int, end_ts: int) -> dict[int, float]:
    curve = {int(point["ts"]): float(point["equity"]) for point in result.get("equity_curve", [])}
    returns: dict[int, float] = {}
    previous = float(result.get("initial_equity", 100_000.0))
    start_day = start_ts // DAY_MS * DAY_MS
    end_day = end_ts // DAY_MS * DAY_MS
    for day in range(start_day, end_day + DAY_MS, DAY_MS):
        equity = curve.get(day, previous)
        returns[day] = equity / previous - 1.0 if previous > 0 else 0.0
        previous = equity
    return returns


def monthly_returns(daily: dict[int, float]) -> dict[str, float]:
    compounded: dict[str, float] = {}
    for ts, value in sorted(daily.items()):
        month = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")
        compounded[month] = (1.0 + compounded.get(month, 0.0)) * (1.0 + value) - 1.0
    return compounded


def active_days(positions: list[dict[str, Any]]) -> set[int]:
    days: set[int] = set()
    for position in positions:
        start = int(position["entry_ts"]) // DAY_MS * DAY_MS
        end = int(position["exit_ts"]) // DAY_MS * DAY_MS
        days.update(range(start, end + DAY_MS, DAY_MS))
    return days


def overlap_coefficient(left: set[int], right: set[int]) -> float:
    denominator = min(len(left), len(right))
    return round(len(left & right) / denominator, 6) if denominator else 0.0


def jaccard(left: set[int], right: set[int]) -> float:
    union = left | right
    return round(len(left & right) / len(union), 6) if union else 0.0


def event_interval_overlap(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, float | int]:
    left_hits: set[int] = set()
    right_hits: set[int] = set()
    overlapping_pairs = 0
    same_symbol_pairs = 0
    for left_index, left_event in enumerate(left):
        left_start = int(left_event["entry_ts"])
        left_end = int(left_event["exit_ts"])
        for right_index, right_event in enumerate(right):
            if left_start > int(right_event["exit_ts"]) or int(right_event["entry_ts"]) > left_end:
                continue
            left_hits.add(left_index)
            right_hits.add(right_index)
            overlapping_pairs += 1
            if str(left_event.get("symbol")) == str(right_event.get("symbol")):
                same_symbol_pairs += 1
    return {
        "overlapping_event_pairs": overlapping_pairs,
        "same_symbol_overlapping_pairs": same_symbol_pairs,
        "left_events_with_any_overlap": len(left_hits),
        "right_events_with_any_overlap": len(right_hits),
        "left_event_overlap_rate": round(len(left_hits) / len(left), 6) if left else 0.0,
        "right_event_overlap_rate": round(len(right_hits) / len(right), 6) if right else 0.0,
    }


def rename_events(events: list[dict[str, Any]], component: str) -> list[dict[str, Any]]:
    return [{**event, "component_id": component} for event in events]


def component_events(
    drift: dict[str, Any],
    uptrend: dict[str, Any],
    coverage: dict[str, Any],
    universe: dict[str, Any],
    data_dir: Path,
) -> dict[str, list[dict[str, Any]]]:
    drift_events = candidate_events_from_result(drift.get("aggregate", {}))
    uptrend_panel = (
        uptrend.get("components", {})
        .get("persistent_uptrend_ema20_reclaim", {})
        .get("primary_constant_universe", {})
        .get("aggregate", {})
    )
    uptrend_events = candidate_events_from_result(uptrend_panel)
    symbols = eligible_symbols(coverage)
    all_downtrend, _inputs = generate_frozen_events(
        data_dir,
        symbols,
        parse_day(DATA_START),
        parse_day(DATA_END, end=True),
    )
    ema_events = expanding_panel_events(
        [event for event in all_downtrend if event.get("component_id") == EMA_COMPONENT],
        universe,
    )
    return {
        DRIFT: rename_events(drift_events, DRIFT),
        UPTREND: rename_events(uptrend_events, UPTREND),
        DOWNTREND: rename_events(ema_events, DOWNTREND),
    }


def simulate_components(
    events_by_component: dict[str, list[dict[str, Any]]],
    price_maps: dict[str, dict[int, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        component: simulate_portfolio(
            events,
            price_maps,
            initial_capital=100_000.0,
            max_positions=MAX_POSITIONS,
            position_fraction=POSITION_FRACTION,
            priority_mode="event_score_then_symbol",
            one_position_per_symbol=True,
        )
        for component, events in events_by_component.items()
    }


def pair_reasons(left: dict[str, Any], right: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for label, result in (("left", left), ("right", right)):
        if int(result.get("accepted_positions", 0)) < 30:
            reasons.append(f"{label} accepted positions {result.get('accepted_positions', 0)} < 30")
        if float(result.get("total_return_pct", 0.0)) <= 0:
            reasons.append(f"{label} standalone return {result.get('total_return_pct', 0.0):+.6f}% <= 0%")
    if float(metrics["active_union_daily_return_correlation"]) > 0.35:
        reasons.append("active-union daily return correlation > 0.35")
    if float(metrics["monthly_return_correlation"]) > 0.50:
        reasons.append("monthly return correlation > 0.50")
    if float(metrics["negative_day_overlap_coefficient"]) > 0.35:
        reasons.append("negative-day overlap coefficient > 0.35")
    if float(metrics["active_day_jaccard"]) > 0.50:
        reasons.append("active-day Jaccard overlap > 0.50")
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
            "top_positive_month_share",
        )
    }


def build_report(
    drift: dict[str, Any],
    uptrend: dict[str, Any],
    coverage: dict[str, Any],
    universe: dict[str, Any],
    data_dir: Path,
) -> dict[str, Any]:
    events_by_component = component_events(drift, uptrend, coverage, universe, data_dir)
    price_maps = load_price_maps(data_dir, eligible_symbols(coverage))
    simulations = simulate_components(events_by_component, price_maps)
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
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
    restricted_pairs: list[str] = []
    for left_name, right_name in combinations(COMPONENTS, 2):
        active_union = sorted(active[left_name] | active[right_name])
        common_months = sorted(set(monthly[left_name]) | set(monthly[right_name]))
        negative_left = {day for day, value in daily[left_name].items() if value < 0}
        negative_right = {day for day, value in daily[right_name].items() if value < 0}
        metrics = {
            "active_union_daily_return_correlation": pearson(
                [daily[left_name].get(day, 0.0) for day in active_union],
                [daily[right_name].get(day, 0.0) for day in active_union],
            ),
            "monthly_return_correlation": pearson(
                [monthly[left_name].get(month, 0.0) for month in common_months],
                [monthly[right_name].get(month, 0.0) for month in common_months],
            ),
            "active_day_jaccard": jaccard(active[left_name], active[right_name]),
            "negative_day_overlap_coefficient": overlap_coefficient(negative_left, negative_right),
            "active_days_left": len(active[left_name]),
            "active_days_right": len(active[right_name]),
            "negative_days_left": len(negative_left),
            "negative_days_right": len(negative_right),
            "event_overlap": event_interval_overlap(
                simulations[left_name].get("closed_positions", []),
                simulations[right_name].get("closed_positions", []),
            ),
        }
        reasons = pair_reasons(simulations[left_name], simulations[right_name], metrics)
        pair_id = f"{left_name}__{right_name}"
        pairs[pair_id] = {
            "left": left_name,
            "right": right_name,
            "metrics": metrics,
            "restriction_reasons": reasons,
            "eligible_for_restricted_observed_combo_simulation": not reasons,
        }
        if not reasons:
            restricted_pairs.append(pair_id)
    return {
        "report_type": "weak_component_complementarity_audit",
        "report_date": "2026-07-13",
        "scope": "observed_data_meta_audit_not_portfolio_backtest",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "normalization": {"position_fraction": POSITION_FRACTION, "max_positions": MAX_POSITIONS},
        "components": {name: summarize_result(result) for name, result in simulations.items()},
        "pairs": pairs,
        "restricted_combo_pairs": restricted_pairs,
        "ready_for_restricted_observed_combo_simulation": bool(restricted_pairs),
        "methodology_notes": [
            "Underlying component rules are unchanged.",
            "The EMA short component is rebuilt over observed data and restricted to fold-eligible symbols.",
            "Daily correlation is measured only on the union of pair-active days to avoid dilution by idle zeros.",
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
        "# Weak Component Complementarity Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Observed-data meta-audit. This is not a combined portfolio backtest.",
        "",
        "## Standalone Normalized Components",
        "",
        "| Component | Accepted | Return | Max DD | Win | Avg Exposure | Month Concentration |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, item in report["components"].items():
        lines.append(
            f"| `{name}` | {item['accepted_positions']} | {item['total_return_pct']:+.6f}% | "
            f"{item['max_drawdown_pct']:.6f}% | {item['realized_win_rate']:.2%} | "
            f"{item['average_gross_exposure']:.2%} | {item['top_positive_month_share']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Pair Complementarity",
            "",
            "| Pair | Daily Corr | Monthly Corr | Active Jaccard | Negative Overlap | Same-Symbol Overlaps | Eligible |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for pair_id, item in report["pairs"].items():
        metrics = item["metrics"]
        lines.append(
            f"| `{pair_id}` | {metrics['active_union_daily_return_correlation']:+.4f} | "
            f"{metrics['monthly_return_correlation']:+.4f} | {metrics['active_day_jaccard']:.2%} | "
            f"{metrics['negative_day_overlap_coefficient']:.2%} | "
            f"{metrics['event_overlap']['same_symbol_overlapping_pairs']} | "
            f"`{str(item['eligible_for_restricted_observed_combo_simulation']).lower()}` |"
        )
    lines.extend(["", "## Decisions", ""])
    for pair_id, item in report["pairs"].items():
        decision = (
            "may proceed to a separate restricted observed-data combo simulation"
            if not item["restriction_reasons"]
            else "; ".join(item["restriction_reasons"])
        )
        lines.append(f"- `{pair_id}`: {decision}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- this report does not combine capital or approve a portfolio",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit complementarity among frozen weak components.")
    parser.add_argument("--drift", type=Path, default=Path("reports/low_volatility_drift_fixed_risk_audit.json"))
    parser.add_argument("--uptrend", type=Path, default=Path("reports/persistent_uptrend_entry_batch_audit.json"))
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/weak_component_complementarity_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/weak_component_complementarity_audit_2026-07-13.md"))
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
    for name, item in report["components"].items():
        print(f"{name}: accepted={item['accepted_positions']}, return={item['total_return_pct']:+.6f}%")
    print(f"restricted_pairs={report['restricted_combo_pairs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
