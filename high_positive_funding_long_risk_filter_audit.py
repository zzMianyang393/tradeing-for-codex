"""Post-hoc audit of high-positive funding as a long-entry crowding warning."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from daily_volume_shock_reversal_audit import LATE_FOLDS, PRIMARY_START, late_constant_symbols
from funding_term_price_alignment_preflight import funding_state, load_funding, rolling_funding
from low_volatility_drift_fixed_risk_audit import candidate_events_from_result
from regime_component_walk_forward_audit import DATA_END, load_json, parse_day
from weekly_range_microtrend_continuation_audit import (
    LONG_COMPONENT as RANGE_LONG,
    generate_events as generate_range_events,
)


DRIFT_LONG = "low_volatility_drift_bb_breakout_fixed_risk_v1_long"
UPTREND_LONG = "persistent_uptrend_ema20_reclaim_v1"
COMPONENTS = (DRIFT_LONG, UPTREND_LONG, RANGE_LONG)


def event_net_outcome_pct(event: dict[str, Any]) -> float | None:
    if "net_return_pct" in event:
        return float(event["net_return_pct"])
    if "realized_return_pct" in event:
        return float(event["realized_return_pct"])
    return None


def rename_long_events(events: list[dict[str, Any]], component: str) -> list[dict[str, Any]]:
    renamed: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("direction", "long")) != "long" or event_net_outcome_pct(event) is None:
            continue
        renamed.append({**event, "component_id": component})
    return renamed


def source_events(
    drift: dict[str, Any],
    uptrend: dict[str, Any],
    universe: dict[str, Any],
    data_dir: Path,
) -> dict[str, list[dict[str, Any]]]:
    drift_events = rename_long_events(candidate_events_from_result(drift.get("aggregate", {})), DRIFT_LONG)
    uptrend_result = (
        uptrend.get("components", {})
        .get("persistent_uptrend_ema20_reclaim", {})
        .get("primary_constant_universe", {})
        .get("aggregate", {})
    )
    uptrend_events = rename_long_events(candidate_events_from_result(uptrend_result), UPTREND_LONG)
    symbols = late_constant_symbols(universe)
    range_events = rename_long_events(
        generate_range_events(data_dir, symbols, parse_day(PRIMARY_START), parse_day(DATA_END, end=True)),
        RANGE_LONG,
    )
    return {DRIFT_LONG: drift_events, UPTREND_LONG: uptrend_events, RANGE_LONG: range_events}


def annotate_funding_state(events: list[dict[str, Any]], data_dir: Path) -> list[dict[str, Any]]:
    rolling_by_symbol: dict[str, list[tuple[int, float]]] = {}
    annotated: list[dict[str, Any]] = []
    for event in events:
        symbol = str(event.get("symbol"))
        if symbol not in rolling_by_symbol:
            path = data_dir / f"{symbol}_funding.csv"
            rolling_by_symbol[symbol] = rolling_funding(load_funding(path)) if path.exists() else []
        state = funding_state(rolling_by_symbol[symbol], int(event.get("entry_ts", 0)))
        outcome = event_net_outcome_pct(event)
        if state is None or outcome is None:
            continue
        annotated.append(
            {
                "component_id": str(event.get("component_id")),
                "symbol": symbol,
                "entry_ts": int(event.get("entry_ts", 0)),
                "entry_date_utc": datetime.fromtimestamp(
                    int(event.get("entry_ts", 0)) / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d"),
                "funding_state": str(state["state"]),
                "event_net_outcome_pct": outcome,
            }
        )
    return annotated


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(event["event_net_outcome_pct"]) for event in events]
    return {
        "events": len(values),
        "mean_net_outcome_pct": round(mean(values), 6) if values else 0.0,
        "sum_net_outcome_pct": round(sum(values), 6),
        "positive_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
    }


def events_in_fold(events: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    start_ts = parse_day(start)
    end_ts = parse_day(end, end=True)
    return [event for event in events if start_ts <= int(event["entry_ts"]) <= end_ts]


def filter_reasons(high: dict[str, Any], other: dict[str, Any], high_folds: dict[str, dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if int(high.get("events", 0)) < 30:
        reasons.append(f"high-positive events {high.get('events', 0)} < 30")
    if float(high.get("mean_net_outcome_pct", 0.0)) >= 0:
        reasons.append(f"high-positive mean {high.get('mean_net_outcome_pct', 0.0):+.6f}% >= 0%")
    gap = float(high.get("mean_net_outcome_pct", 0.0)) - float(other.get("mean_net_outcome_pct", 0.0))
    if gap > -0.25:
        reasons.append(f"high-minus-other mean gap {gap:+.6f}pp > -0.25pp")
    negative_folds = sum(
        int(item.get("events", 0)) >= 10 and float(item.get("mean_net_outcome_pct", 0.0)) < 0
        for item in high_folds.values()
    )
    if negative_folds < 2:
        reasons.append(f"qualified negative folds {negative_folds}/3 < 2/3")
    return reasons


def build_report(
    drift: dict[str, Any],
    uptrend: dict[str, Any],
    universe: dict[str, Any],
    data_dir: Path,
) -> dict[str, Any]:
    by_component = source_events(drift, uptrend, universe, data_dir)
    annotated_by_component = {
        component: annotate_funding_state(events, data_dir)
        for component, events in by_component.items()
    }
    all_events = [event for events in annotated_by_component.values() for event in events]
    high_events = [event for event in all_events if event["funding_state"] == "high_positive"]
    other_events = [event for event in all_events if event["funding_state"] != "high_positive"]
    high_folds = {
        name: summarize(events_in_fold(high_events, start, end))
        for name, start, end in LATE_FOLDS
    }
    high_summary = summarize(high_events)
    other_summary = summarize(other_events)
    reasons = filter_reasons(high_summary, other_summary, high_folds)
    components: dict[str, Any] = {}
    for component, events in annotated_by_component.items():
        high = [event for event in events if event["funding_state"] == "high_positive"]
        other = [event for event in events if event["funding_state"] != "high_positive"]
        components[component] = {
            "all": summarize(events),
            "high_positive": summarize(high),
            "other": summarize(other),
            "high_minus_other_mean_percentage_points": round(
                summarize(high)["mean_net_outcome_pct"] - summarize(other)["mean_net_outcome_pct"], 6
            ),
        }
    return {
        "report_type": "high_positive_funding_long_risk_filter_audit",
        "report_date": "2026-07-14",
        "scope": "posthoc_meta_only_existing_long_event_diagnostic",
        "window": {"start": PRIMARY_START, "end": DATA_END},
        "components": components,
        "aggregate_high_positive": high_summary,
        "aggregate_other": other_summary,
        "high_minus_other_mean_percentage_points": round(
            high_summary["mean_net_outcome_pct"] - other_summary["mean_net_outcome_pct"], 6
        ),
        "high_positive_folds": high_folds,
        "filter_reasons": reasons,
        "status": "posthoc_risk_filter_watchlist" if not reasons else "posthoc_filter_rejected",
        "allowed_as_hard_filter": False,
        "historical_filtered_backtest_authorized": False,
        "methodology_notes": [
            "Existing event rules and outcomes are not changed.",
            "This audit was motivated by a failed funding directional rule and is post-hoc.",
            "Passing can create only a prospective risk-filter observation.",
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
        "# High-Positive Funding Long Risk Filter Audit",
        "",
        "Date: 2026-07-14",
        "",
        "Post-hoc meta-only diagnostic. No historical filtered backtest is authorized.",
        "",
        "## Aggregate",
        "",
        f"- high-positive events: {report['aggregate_high_positive']['events']}",
        f"- high-positive mean: {report['aggregate_high_positive']['mean_net_outcome_pct']:+.6f}%",
        f"- other-state mean: {report['aggregate_other']['mean_net_outcome_pct']:+.6f}%",
        f"- high-minus-other gap: {report['high_minus_other_mean_percentage_points']:+.6f}pp",
        f"- status: `{report['status']}`",
        "",
        "## Components",
        "",
        "| Component | High Events | High Mean | Other Events | Other Mean | Gap |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for component, item in report["components"].items():
        lines.append(
            f"| `{component}` | {item['high_positive']['events']} | "
            f"{item['high_positive']['mean_net_outcome_pct']:+.6f}% | {item['other']['events']} | "
            f"{item['other']['mean_net_outcome_pct']:+.6f}% | "
            f"{item['high_minus_other_mean_percentage_points']:+.6f}pp |"
        )
    lines.extend(["", "## High-Positive Funding Folds", ""])
    for name, item in report["high_positive_folds"].items():
        lines.append(f"- `{name}`: {item['events']} events, {item['mean_net_outcome_pct']:+.6f}% mean")
    lines.extend(["", "## Decision Reasons", ""])
    if report["filter_reasons"]:
        lines.extend(f"- {reason}" for reason in report["filter_reasons"])
    else:
        lines.append("- Retain for prospective risk-filter observation only.")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- hard filter allowed: `false`",
            "- historical filtered backtest authorized: `false`",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit high-positive funding as a long risk filter.")
    parser.add_argument("--drift", type=Path, default=Path("reports/low_volatility_drift_fixed_risk_audit.json"))
    parser.add_argument("--uptrend", type=Path, default=Path("reports/persistent_uptrend_entry_batch_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/high_positive_funding_long_risk_filter_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/high_positive_funding_long_risk_filter_audit_2026-07-14.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.drift), load_json(args.uptrend), load_json(args.universe), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"high_events={report['aggregate_high_positive']['events']}, "
        f"high_mean={report['aggregate_high_positive']['mean_net_outcome_pct']:+.6f}%, "
        f"gap={report['high_minus_other_mean_percentage_points']:+.6f}pp, status={report['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
