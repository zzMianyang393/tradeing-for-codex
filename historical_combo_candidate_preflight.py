"""Preflight frozen weak factors for historical combo-hypothesis research.

This is deliberately a selection audit, not a backtester. It evaluates only
already-normalized, regime-compatible historical feature events. A factor that
failed as a standalone strategy may be studied as a weak feature, but it must
first clear coverage and semantic-integrity checks. Concentration is preserved
as an explicit portfolio penalty rather than silently discarded.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


MIN_EVENTS = 30
MIN_ACTIVE_MONTHS = 12
MAX_POSITIVE_MONTH_CONCENTRATION = 0.25
MIN_DIRECTIONAL_FEATURES = 3
SEMANTIC_REPAIR_TAG = "posthoc_semantic_repair_requires_future_oos"


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def source_tags(preflight: dict[str, Any]) -> dict[str, list[str]]:
    return {
        item["source_research_id"]: list(item.get("tags", []))
        for item in preflight.get("groups", {}).get("directional_feature_candidates", [])
        if item.get("source_research_id")
    }


def summarize_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        feature_id = event.get("feature_id")
        if feature_id:
            grouped[str(feature_id)].append(event)

    summaries: dict[str, dict[str, Any]] = {}
    for feature_id, rows in sorted(grouped.items()):
        active_months = sorted({str(row.get("month", "")) for row in rows if row.get("month")})
        positive_by_month: dict[str, float] = defaultdict(float)
        for row in rows:
            value = float(row.get("net_return_pct", 0.0))
            month = str(row.get("month", ""))
            if value > 0 and month:
                positive_by_month[month] += value
        total_positive = sum(positive_by_month.values())
        top_share = max(positive_by_month.values(), default=0.0) / total_positive if total_positive else 0.0
        summaries[feature_id] = {
            "source_research_id": rows[0].get("source_research_id", ""),
            "event_count": len(rows),
            "active_months": active_months,
            "active_month_count": len(active_months),
            "top_positive_month_contribution_share": round(top_share, 6),
        }
    return summaries


def classify(summary: dict[str, Any], tags: list[str]) -> tuple[str, list[str]]:
    hard_reasons: list[str] = []
    if summary["event_count"] < MIN_EVENTS:
        hard_reasons.append(f"events_below_{MIN_EVENTS}")
    if summary["active_month_count"] < MIN_ACTIVE_MONTHS:
        hard_reasons.append(f"active_months_below_{MIN_ACTIVE_MONTHS}")
    if SEMANTIC_REPAIR_TAG in tags:
        hard_reasons.append("requires_future_oos_semantic_confirmation")

    if hard_reasons:
        return "not_eligible_for_historical_combo_hypothesis", hard_reasons
    if summary["top_positive_month_contribution_share"] > MAX_POSITIVE_MONTH_CONCENTRATION:
        return "eligible_with_concentration_penalty", ["positive_month_concentration_above_limit"]
    return "eligible_for_historical_combo_hypothesis", []


def build_report(timeseries: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
    tags_by_source = source_tags(preflight)
    summaries = summarize_events(list(timeseries.get("events", [])))
    features: list[dict[str, Any]] = []
    for feature_id, summary in summaries.items():
        source_id = summary["source_research_id"]
        status, reasons = classify(summary, tags_by_source.get(source_id, []))
        features.append({
            "feature_id": feature_id,
            **summary,
            "source_tags": tags_by_source.get(source_id, []),
            "status": status,
            "reasons": reasons,
            "allowed_as_standalone": False,
            "eligible_for_paper": False,
        })

    strict_eligible = [item for item in features if item["status"] == "eligible_for_historical_combo_hypothesis"]
    penalty_eligible = [item for item in features if item["status"] == "eligible_with_concentration_penalty"]
    hypothesis_eligible = strict_eligible + penalty_eligible
    ready = len(hypothesis_eligible) >= MIN_DIRECTIONAL_FEATURES
    return {
        "report_type": "historical_combo_candidate_preflight",
        "scope": "regime_compatible_historical_feature_selection_not_combo_backtest",
        "thresholds": {
            "min_events": MIN_EVENTS,
            "min_active_months": MIN_ACTIVE_MONTHS,
            "max_positive_month_concentration": MAX_POSITIVE_MONTH_CONCENTRATION,
            "min_directional_features": MIN_DIRECTIONAL_FEATURES,
        },
        "features": features,
        "eligible_directional_feature_ids": [item["feature_id"] for item in strict_eligible],
        "concentration_penalty_feature_ids": [item["feature_id"] for item in penalty_eligible],
        "hypothesis_directional_feature_ids": [item["feature_id"] for item in hypothesis_eligible],
        "ready_for_historical_combo_hypothesis": ready,
        "allowed_next_step": "frozen_combo_hypothesis_specification" if ready else "expand_frozen_directional_feature_coverage",
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "Only pre-existing, regime-compatible events are assessed.",
            "Standalone rejection does not become standalone approval.",
            "A concentration-penalty feature must have capped contribution in any later hypothesis.",
            "Semantic-repair candidates require independent future OOS confirmation.",
            "No weights, positions, orders, or execution logic are produced.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight weak factors for historical combo research.")
    parser.add_argument("--timeseries", type=Path, default=Path("reports/combo_feature_timeseries.json"))
    parser.add_argument("--preflight", type=Path, default=Path("reports/feature_pool_preflight_review.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/historical_combo_candidate_preflight.json"))
    args = parser.parse_args(argv)
    timeseries = load_json(args.timeseries)
    preflight = load_json(args.preflight)
    if not timeseries or not preflight:
        print("ERROR: Cannot load required feature reports")
        return 1
    report = build_report(timeseries, preflight)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Hypothesis directional features: {len(report['hypothesis_directional_feature_ids'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
