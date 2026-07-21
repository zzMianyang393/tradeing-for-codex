"""Seal the failed shared-capital combo as diagnostic-only historical research.

The shared-capital baseline and its leave-one-sleeve-out figures explain a
historical failure.  They must not become a post-hoc subset-selection process,
a feature, or a paper-trading candidate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


COMBO_RESEARCH_ID = "regime_component_shared_capital_combo"


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def find_record(registry: dict[str, Any], research_id: str) -> dict[str, Any] | None:
    for record in registry.get("records", []):
        if record.get("research_id") == research_id:
            return record
    return None


def combo_features(feature_pool: dict[str, Any], research_id: str) -> list[dict[str, Any]]:
    return [
        feature for feature in feature_pool.get("features", [])
        if feature.get("source_research_id") == research_id
    ]


def build_seal(
    combo_audit: dict[str, Any] | None,
    registry: dict[str, Any] | None,
    feature_pool: dict[str, Any] | None,
    preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a read-only proof that diagnostics cannot revive the combo."""
    issues: list[str] = []
    combo = (combo_audit or {}).get("shared_capital_combo", {})
    diagnostics = combo.get("leave_one_sleeve_out", {})
    record = find_record(registry or {}, COMBO_RESEARCH_ID)
    features = combo_features(feature_pool or {}, COMBO_RESEARCH_ID)

    combo_rejected = combo.get("status") == "historical_walk_forward_rejected"
    if not combo_rejected:
        issues.append("Shared-capital baseline is not marked historical_walk_forward_rejected.")

    expected_components = {
        "uptrend_donchian_55_20_long",
        "uptrend_supertrend_4h_long",
        "range_bb_reversion_4h",
        "range_rsi_reversion_4h",
    }
    diagnostics_are_fixed = set(diagnostics) == expected_components and len(diagnostics) == 4
    if not diagnostics_are_fixed:
        issues.append("Leave-one-sleeve-out diagnostics are not the fixed four-sleeve set.")

    diagnostics_not_candidates = bool(diagnostics) and all(
        item.get("diagnostic_only") is True and item.get("not_a_candidate") is True
        for item in diagnostics.values()
    )
    if not diagnostics_not_candidates:
        issues.append("At least one leave-one-sleeve-out result is not explicitly diagnostic-only.")

    registry_rejected = bool(record) and record.get("status") == "rejected" and record.get("eligible_for_paper") is False
    if not registry_rejected:
        issues.append("Registry does not reject the shared-capital combo with paper eligibility disabled.")

    feature_blocked = len(features) == 1 and all(
        feature.get("feature_role") == "blocked"
        and feature.get("allowed_in_combo_research") is False
        and feature.get("allowed_as_standalone_strategy") is False
        and feature.get("eligible_for_paper") is False
        for feature in features
    )
    if not feature_blocked:
        issues.append("Feature pool does not hard-block the shared-capital combo.")

    blocked_features = (preflight or {}).get("groups", {}).get("blocked_features", [])
    preflight_blocked = bool(preflight) and any(
        item.get("source_research_id") == COMBO_RESEARCH_ID
        for item in blocked_features
    )
    if not preflight_blocked:
        issues.append("Feature-pool preflight does not list the shared-capital combo as blocked.")

    safety_gates = (combo_audit or {}).get("safety_gates", {})
    gates_closed = (
        safety_gates.get("approved_for_paper") == []
        and safety_gates.get("eligible_for_paper") is False
        and safety_gates.get("safe_to_enable_trading") is False
        and safety_gates.get("ready_for_combo_backtest") is False
    )
    if not gates_closed:
        issues.append("Historical combo safety gates are not all closed.")

    return {
        "audit_type": "shared_capital_combo_diagnostic_seal",
        "audit_date": "2026-07-15",
        "research_id": COMBO_RESEARCH_ID,
        "historical_diagnostic_only": True,
        "seal_status": "sealed" if not issues else "invalid",
        "issues": issues,
        "checks": {
            "baseline_rejected": combo_rejected,
            "fixed_four_sleeve_diagnostics": diagnostics_are_fixed,
            "all_diagnostics_not_candidates": diagnostics_not_candidates,
            "registry_rejected_not_paper_eligible": registry_rejected,
            "feature_pool_hard_blocked": feature_blocked,
            "preflight_lists_blocked": preflight_blocked,
            "all_combo_safety_gates_closed": gates_closed,
        },
        "diagnostic_count": len(diagnostics),
        "prohibitions": [
            "Do not select a leave-one-sleeve-out subset as a candidate.",
            "Do not turn the historical combo into a directional feature.",
            "Do not change a sleeve definition or allocation from these diagnostics.",
            "Do not use this audit to enable paper or live trading.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Shared-Capital Combo Diagnostic Seal",
        "",
        "Date: 2026-07-15",
        "",
        "This document seals a failed historical diagnostic. It does not select a subset or create a new strategy.",
        "",
        f"Status: `{report['seal_status']}`",
        "",
        "## Verified Boundaries",
        "",
    ]
    for name, value in report["checks"].items():
        lines.append(f"- `{name}`: `{str(value).lower()}`")
    lines.extend(["", "## Prohibitions", ""])
    lines.extend(f"- {item}" for item in report["prohibitions"])
    if report["issues"]:
        lines.extend(["", "## Issues", ""])
        lines.extend(f"- {item}" for item in report["issues"])
    lines.extend(["", "No allocation, sleeve, or candidate is promoted by this seal.", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal shared-capital combo diagnostics.")
    parser.add_argument("--combo-audit", type=Path, default=Path("reports/regime_component_walk_forward_audit.json"))
    parser.add_argument("--registry", type=Path, default=Path("reports/research_approval_registry.json"))
    parser.add_argument("--feature-pool", type=Path, default=Path("reports/strategy_feature_pool.json"))
    parser.add_argument("--preflight", type=Path, default=Path("reports/feature_pool_preflight_review.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/shared_capital_combo_diagnostic_seal.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/shared_capital_combo_diagnostic_seal_2026-07-15.md"))
    args = parser.parse_args(argv)

    report = build_seal(
        load_json(args.combo_audit),
        load_json(args.registry),
        load_json(args.feature_pool),
        load_json(args.preflight),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"seal_status={report['seal_status']}; issues={len(report['issues'])}")
    return 0 if report["seal_status"] == "sealed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
