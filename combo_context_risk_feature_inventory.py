"""Inventory context and risk-filter features for combo research.

This module checks whether non-directional combo features have enough evidence
to be converted into read-only time series later. It does not build a combo
model, does not assign weights, and does not approve trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


GROUP_ROLE_MAP = {
    "context_label_candidates": "context_label",
    "risk_filter_candidates": "risk_filter_candidate",
}

EXTRACTABILITY_PRIORITY = {
    "missing_evidence": 0,
    "document_only": 1,
    "aggregate_only": 2,
    "preview_only": 3,
    "event_series_available": 4,
}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def feature_lookup(feature_pool: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item.get("source_research_id", ""): item
        for item in feature_pool.get("features", [])
        if item.get("source_research_id")
    }


def classify_evidence_path(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    result: dict[str, Any] = {
        "path": path_value,
        "exists": path.exists(),
        "kind": "missing_evidence",
        "event_count": 0,
        "preview_count": 0,
    }
    if not path.exists():
        return result

    if path.suffix.lower() != ".json":
        result["kind"] = "document_only"
        return result

    data = load_json(path)
    if data is None:
        result["kind"] = "aggregate_only"
        result["parse_error"] = True
        return result

    events = data.get("events")
    preview = data.get("event_preview")
    if isinstance(events, list) and events:
        result["kind"] = "event_series_available"
        result["event_count"] = len(events)
    elif isinstance(preview, list) and preview:
        result["kind"] = "preview_only"
        result["preview_count"] = len(preview)
    else:
        result["kind"] = "aggregate_only"
    return result


def strongest_extractability(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "missing_evidence"
    return max(evidence, key=lambda item: EXTRACTABILITY_PRIORITY[item["kind"]])["kind"]


def recommended_next_step(role: str, extractability: str) -> str:
    if extractability == "event_series_available":
        if role == "risk_filter_candidate":
            return "extract_veto_series"
        return "extract_context_event_series"
    if extractability == "preview_only":
        return "regenerate_full_event_report_before_series_extraction"
    if extractability == "aggregate_only":
        if role == "risk_filter_candidate":
            return "derive_veto_schema_only_after_manual_review"
        return "keep_context_metadata_until_schema_defined"
    if extractability == "document_only":
        return "keep_metadata_only"
    return "blocked_until_evidence_report_exists"


def inventory_item(item: dict[str, Any], role: str, pool_by_research_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    research_id = item.get("source_research_id", "")
    pool_item = pool_by_research_id.get(research_id, {})
    evidence_paths = pool_item.get("evidence_paths", [])
    evidence = [classify_evidence_path(path) for path in evidence_paths]
    extractability = strongest_extractability(evidence)
    event_count = sum(path["event_count"] for path in evidence)
    preview_count = sum(path["preview_count"] for path in evidence)

    return {
        "feature_id": item.get("feature_id", ""),
        "source_research_id": research_id,
        "role": role,
        "tags": item.get("tags", []),
        "extractability": extractability,
        "event_count": event_count,
        "preview_count": preview_count,
        "evidence_paths": evidence,
        "allowed_as_directional": False,
        "allowed_as_standalone_strategy": False,
        "eligible_for_paper": False,
        "veto_only": role == "risk_filter_candidate",
        "recommended_next_step": recommended_next_step(role, extractability),
    }


def build_inventory(preflight: dict[str, Any], feature_pool: dict[str, Any]) -> dict[str, Any]:
    groups = preflight.get("groups", {})
    pool_by_research_id = feature_lookup(feature_pool)
    items: list[dict[str, Any]] = []

    for group_name, role in GROUP_ROLE_MAP.items():
        for item in groups.get(group_name, []):
            items.append(inventory_item(item, role, pool_by_research_id))

    counts_by_role: dict[str, int] = {}
    counts_by_extractability: dict[str, int] = {}
    for item in items:
        counts_by_role[item["role"]] = counts_by_role.get(item["role"], 0) + 1
        key = item["extractability"]
        counts_by_extractability[key] = counts_by_extractability.get(key, 0) + 1

    ready_for_series_extraction = [
        item["feature_id"]
        for item in items
        if item["extractability"] == "event_series_available"
    ]

    return {
        "report_type": "combo_context_risk_feature_inventory",
        "report_date": "2026-07-13",
        "scope": "read_only_auxiliary_feature_extractability",
        "n_features": len(items),
        "counts_by_role": dict(sorted(counts_by_role.items())),
        "counts_by_extractability": dict(sorted(counts_by_extractability.items())),
        "ready_for_series_extraction": ready_for_series_extraction,
        "features": items,
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "Only context labels and risk filters are inventoried.",
            "Risk filters are veto-only and cannot become directional signals.",
            "This report does not run a combo backtest or approve paper trading.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory context/risk combo features.")
    parser.add_argument("--preflight", type=Path, default=Path("reports/feature_pool_preflight_review.json"))
    parser.add_argument("--feature-pool", type=Path, default=Path("reports/strategy_feature_pool.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/combo_context_risk_feature_inventory.json"))
    args = parser.parse_args(argv)

    preflight = load_json(args.preflight)
    feature_pool = load_json(args.feature_pool)
    if not preflight:
        print("ERROR: Cannot load feature pool preflight report")
        return 1
    if not feature_pool:
        print("ERROR: Cannot load strategy feature pool report")
        return 1

    report = build_inventory(preflight, feature_pool)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Features: {report['n_features']}")
    print(f"Ready for series extraction: {len(report['ready_for_series_extraction'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
