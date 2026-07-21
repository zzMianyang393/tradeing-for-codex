"""Attribute maximum drawdown episodes of restricted weak-component pairs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from downtrend_rebound_capital_constrained_simulator import marked_position_value, price_at, simulate_portfolio
from low_volatility_drift_fixed_risk_audit import load_price_maps
from regime_component_walk_forward_audit import DAY_MS, eligible_symbols, load_json
from restricted_weak_pair_combo_simulation import MAX_POSITIONS, POSITION_FRACTION, run_shared
from weak_component_complementarity_audit import component_events


def format_day(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def drawdown_episode(result: dict[str, Any]) -> dict[str, Any]:
    curve = sorted(result.get("equity_curve", []), key=lambda point: int(point["ts"]))
    if not curve:
        return {
            "peak_ts": None,
            "trough_ts": None,
            "recovery_ts": None,
            "peak_equity": float(result.get("initial_equity", 0.0)),
            "trough_equity": float(result.get("initial_equity", 0.0)),
            "max_drawdown_pct": 0.0,
            "peak_to_trough_days": 0,
            "recovery_days": None,
        }
    peak_equity = float(result.get("initial_equity", curve[0]["equity"]))
    peak_ts = int(curve[0]["ts"])
    worst = 0.0
    worst_peak_equity = peak_equity
    worst_peak_ts = peak_ts
    trough_equity = peak_equity
    trough_ts = peak_ts
    for point in curve:
        ts = int(point["ts"])
        equity = float(point["equity"])
        if equity > peak_equity:
            peak_equity = equity
            peak_ts = ts
        drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        if drawdown > worst:
            worst = drawdown
            worst_peak_equity = peak_equity
            worst_peak_ts = peak_ts
            trough_equity = equity
            trough_ts = ts
    recovery_ts = next(
        (
            int(point["ts"])
            for point in curve
            if int(point["ts"]) > trough_ts and float(point["equity"]) >= worst_peak_equity
        ),
        None,
    )
    return {
        "peak_ts": worst_peak_ts,
        "peak_date": format_day(worst_peak_ts),
        "trough_ts": trough_ts,
        "trough_date": format_day(trough_ts),
        "recovery_ts": recovery_ts,
        "recovery_date": format_day(recovery_ts),
        "peak_equity": round(worst_peak_equity, 6),
        "trough_equity": round(trough_equity, 6),
        "equity_decline": round(trough_equity - worst_peak_equity, 6),
        "max_drawdown_pct": round(worst * 100.0, 6),
        "peak_to_trough_days": (trough_ts - worst_peak_ts) // DAY_MS,
        "recovery_days": (recovery_ts - trough_ts) // DAY_MS if recovery_ts is not None else None,
    }


def position_cumulative_pnl(
    position: dict[str, Any],
    day_ts: int,
    price_maps: dict[str, dict[int, Any]],
) -> float:
    entry_day = int(position["entry_ts"]) // DAY_MS * DAY_MS
    exit_day = int(position["exit_ts"]) // DAY_MS * DAY_MS
    if day_ts < entry_day:
        return 0.0
    if day_ts >= exit_day:
        return float(position.get("realized_pnl", 0.0))
    symbol = str(position["symbol"])
    mark = price_at(price_maps, symbol, day_ts, "close", float(position["entry_price"]))
    return marked_position_value(position, mark) - float(position["cash_outlay"])


def component_pnl_curves(
    result: dict[str, Any],
    price_maps: dict[str, dict[int, Any]],
    components: tuple[str, str],
) -> dict[str, dict[int, float]]:
    days = [int(point["ts"]) for point in result.get("equity_curve", [])]
    positions_by_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for position in result.get("closed_positions", []):
        positions_by_component[str(position.get("component_id"))].append(position)
    return {
        component: {
            day: sum(position_cumulative_pnl(position, day, price_maps) for position in positions_by_component[component])
            for day in days
        }
        for component in components
    }


def failure_classification(changes: dict[str, float]) -> dict[str, Any]:
    losses = {name: abs(value) for name, value in changes.items() if value < 0}
    if len(losses) < 2:
        return {
            "classification": "offsetting_component",
            "smaller_loss_share": 0.0,
            "common_failure": False,
        }
    total = sum(losses.values())
    smaller_share = min(losses.values()) / total if total else 0.0
    classification = "common_failure" if smaller_share >= 0.20 else "minor_additive_loss"
    return {
        "classification": classification,
        "smaller_loss_share": round(smaller_share, 6),
        "common_failure": classification == "common_failure",
    }


def average_component_exposure(
    result: dict[str, Any], components: tuple[str, str], peak_ts: int, trough_ts: int
) -> dict[str, float]:
    window = [
        point for point in result.get("equity_curve", [])
        if peak_ts <= int(point["ts"]) <= trough_ts
    ]
    return {
        component: round(
            mean(float(point.get("component_exposure", {}).get(component, 0.0)) for point in window), 6
        ) if window else 0.0
        for component in components
    }


def daily_loss_overlap(
    curves: dict[str, dict[int, float]], components: tuple[str, str], peak_ts: int, trough_ts: int
) -> dict[str, Any]:
    days = list(range(peak_ts + DAY_MS, trough_ts + DAY_MS, DAY_MS))
    negative_counts = {component: 0 for component in components}
    joint_negative = 0
    worst_day: int | None = None
    worst_combined_change = 0.0
    previous = {component: curves[component].get(peak_ts, 0.0) for component in components}
    for day in days:
        changes: dict[str, float] = {}
        for component in components:
            current = curves[component].get(day, previous[component])
            changes[component] = current - previous[component]
            previous[component] = current
            if changes[component] < 0:
                negative_counts[component] += 1
        if all(changes[component] < 0 for component in components):
            joint_negative += 1
        combined = sum(changes.values())
        if combined < worst_combined_change:
            worst_combined_change = combined
            worst_day = day
    return {
        "window_days": len(days),
        "negative_days_by_component": negative_counts,
        "joint_negative_days": joint_negative,
        "joint_negative_day_rate": round(joint_negative / len(days), 6) if days else 0.0,
        "worst_combined_component_pnl_day": format_day(worst_day),
        "worst_combined_component_pnl_change": round(worst_combined_change, 6),
    }


def run_standalone(events: list[dict[str, Any]], price_maps: dict[str, dict[int, Any]]) -> dict[str, Any]:
    return simulate_portfolio(
        events,
        price_maps,
        initial_capital=100_000.0,
        max_positions=MAX_POSITIONS,
        position_fraction=POSITION_FRACTION,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
    )


def build_report(
    combo_report: dict[str, Any],
    drift: dict[str, Any],
    uptrend: dict[str, Any],
    coverage: dict[str, Any],
    universe: dict[str, Any],
    data_dir: Path,
) -> dict[str, Any]:
    pair_ids = list(combo_report.get("posthoc_risk_adjusted_combo_watchlist", []))
    events_by_component = component_events(drift, uptrend, coverage, universe, data_dir)
    price_maps = load_price_maps(data_dir, eligible_symbols(coverage))
    standalone_results = {
        component: run_standalone(events, price_maps)
        for component, events in events_by_component.items()
    }
    pairs: dict[str, Any] = {}
    for pair_id in pair_ids:
        components = tuple(pair_id.split("__", 1))
        if len(components) != 2:
            continue
        events = events_by_component[components[0]] + events_by_component[components[1]]
        combo = run_shared(events, price_maps, components)
        episode = drawdown_episode(combo)
        peak_ts = int(episode["peak_ts"])
        trough_ts = int(episode["trough_ts"])
        curves = component_pnl_curves(combo, price_maps, components)
        changes = {
            component: round(curves[component].get(trough_ts, 0.0) - curves[component].get(peak_ts, 0.0), 6)
            for component in components
        }
        classification = failure_classification(changes)
        component_decline = sum(changes.values())
        pairs[pair_id] = {
            "components": list(components),
            "combo_episode": episode,
            "standalone_episodes": {
                component: drawdown_episode(standalone_results[component]) for component in components
            },
            "component_pnl_change_peak_to_trough": changes,
            "component_pnl_decline_sum": round(component_decline, 6),
            "equity_decline_reconciliation_error": round(
                component_decline - float(episode["equity_decline"]), 6
            ),
            "average_component_exposure_in_drawdown": average_component_exposure(
                combo, components, peak_ts, trough_ts
            ),
            "daily_loss_overlap": daily_loss_overlap(curves, components, peak_ts, trough_ts),
            "failure_classification": classification,
            "watchlist_action": (
                "retain_with_common_failure_warning"
                if classification["common_failure"]
                else "retain_without_common_failure_flag"
            ),
        }
    return {
        "report_type": "restricted_combo_drawdown_anatomy_audit",
        "report_date": "2026-07-13",
        "scope": "descriptive_posthoc_drawdown_attribution",
        "pairs": pairs,
        "common_failure_pairs": [
            pair_id for pair_id, item in pairs.items() if item["failure_classification"]["common_failure"]
        ],
        "methodology_notes": [
            "Accepted positions are marked on the same daily calendar used by the shared-capital simulator.",
            "Component cumulative PnL reconciles the pair equity decline within rounding tolerance.",
            "The frozen 20% smaller-loss-share threshold classifies common failure.",
            "No strategy rule or allocation is changed by this audit.",
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
        "# Restricted Combo Drawdown Anatomy Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Descriptive post-hoc attribution. No allocation or strategy rule is changed.",
        "",
        "## Maximum Drawdown Episodes",
        "",
        "| Pair | Peak | Trough | Recovery | Drawdown | Days | Classification |",
        "| --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for pair_id, item in report["pairs"].items():
        episode = item["combo_episode"]
        lines.append(
            f"| `{pair_id}` | {episode['peak_date']} | {episode['trough_date']} | "
            f"{episode['recovery_date'] or 'not recovered'} | {episode['max_drawdown_pct']:.6f}% | "
            f"{episode['peak_to_trough_days']} | `{item['failure_classification']['classification']}` |"
        )
    lines.extend(["", "## Component Attribution", ""])
    for pair_id, item in report["pairs"].items():
        lines.extend(
            [
                f"### `{pair_id}`",
                "",
                "| Component | Peak-to-Trough PnL | Average Exposure | Standalone Max DD |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for component in item["components"]:
            lines.append(
                f"| `{component}` | {item['component_pnl_change_peak_to_trough'][component]:+.6f} | "
                f"{item['average_component_exposure_in_drawdown'][component]:.2%} | "
                f"{item['standalone_episodes'][component]['max_drawdown_pct']:.6f}% |"
            )
        overlap = item["daily_loss_overlap"]
        lines.extend(
            [
                "",
                f"- joint negative days: {overlap['joint_negative_days']}/{overlap['window_days']} "
                f"({overlap['joint_negative_day_rate']:.2%})",
                f"- smaller loss share: {item['failure_classification']['smaller_loss_share']:.2%}",
                f"- reconciliation error: {item['equity_decline_reconciliation_error']:+.6f}",
                f"- action: `{item['watchlist_action']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Safety",
            "",
            "- strict combo gate results remain unchanged",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Attribute maximum drawdowns of restricted combo watchlist pairs.")
    parser.add_argument("--combo", type=Path, default=Path("reports/restricted_weak_pair_combo_simulation.json"))
    parser.add_argument("--drift", type=Path, default=Path("reports/low_volatility_drift_fixed_risk_audit.json"))
    parser.add_argument("--uptrend", type=Path, default=Path("reports/persistent_uptrend_entry_batch_audit.json"))
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/restricted_combo_drawdown_anatomy_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/restricted_combo_drawdown_anatomy_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(
        load_json(args.combo),
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
        episode = item["combo_episode"]
        print(
            f"{pair_id}: {episode['peak_date']}->{episode['trough_date']}, "
            f"dd={episode['max_drawdown_pct']:.6f}%, class={item['failure_classification']['classification']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
