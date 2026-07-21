"""Review monthly combo research matrix quality.

This gate checks coverage, sparsity, and common-sample availability before any
combo hypothesis test is allowed. It does not run a backtest or approve trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MIN_DIRECTIONAL_FEATURES = 3
MIN_COMMON_MONTHS = 12
MAX_DIRECTIONAL_ZERO_SHARE = 0.40
MAX_CONTEXT_ZERO_SHARE = 0.80
MAX_RISK_ZERO_SHARE = 0.40


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def feature_column(feature_id: str, role: str) -> str:
    if role == "directional_weak_signal":
        return f"{feature_id}__net_return_pct"
    return f"{feature_id}__event_count"


def nonzero_months(rows: list[dict[str, Any]], feature_id: str, role: str) -> list[str]:
    column = feature_column(feature_id, role)
    return [row["month"] for row in rows if float(row.get(column, 0.0)) != 0.0]


def coverage_by_feature(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = matrix.get("rows", [])
    n_months = len(rows)
    result: dict[str, dict[str, Any]] = {}
    for feature_id, role in matrix.get("feature_roles", {}).items():
        active_months = nonzero_months(rows, feature_id, role)
        zero_months = [row["month"] for row in rows if row["month"] not in set(active_months)]
        result[feature_id] = {
            "role": role,
            "active_months": len(active_months),
            "zero_months": len(zero_months),
            "active_month_share": round(len(active_months) / n_months, 6) if n_months else 0.0,
            "zero_month_share": round(len(zero_months) / n_months, 6) if n_months else 1.0,
            "first_active_month": active_months[0] if active_months else None,
            "last_active_month": active_months[-1] if active_months else None,
        }
    return result


def role_feature_ids(matrix: dict[str, Any], role: str) -> list[str]:
    return [feature_id for feature_id, value in matrix.get("feature_roles", {}).items() if value == role]


def common_months(rows: list[dict[str, Any]], feature_ids: list[str], roles: dict[str, str]) -> list[str]:
    months: list[str] = []
    for row in rows:
        if all(float(row.get(feature_column(feature_id, roles[feature_id]), 0.0)) != 0.0 for feature_id in feature_ids):
            months.append(row["month"])
    return months


def reason_codes(matrix: dict[str, Any], coverage: dict[str, dict[str, Any]]) -> list[str]:
    rows = matrix.get("rows", [])
    roles = matrix.get("feature_roles", {})
    directional = role_feature_ids(matrix, "directional_weak_signal")
    context = role_feature_ids(matrix, "context_label")
    risk = role_feature_ids(matrix, "risk_filter_candidate")
    reasons: list[str] = []

    if len(directional) < MIN_DIRECTIONAL_FEATURES:
        reasons.append(f"directional features {len(directional)} < {MIN_DIRECTIONAL_FEATURES}")

    directional_common = common_months(rows, directional, roles) if directional else []
    if len(directional_common) < MIN_COMMON_MONTHS:
        reasons.append(f"directional common active months {len(directional_common)} < {MIN_COMMON_MONTHS}")

    for feature_id in directional:
        if coverage[feature_id]["zero_month_share"] > MAX_DIRECTIONAL_ZERO_SHARE:
            reasons.append(f"{feature_id} directional zero-month share {coverage[feature_id]['zero_month_share']:.2%} > 40%")

    for feature_id in context:
        if coverage[feature_id]["zero_month_share"] > MAX_CONTEXT_ZERO_SHARE:
            reasons.append(f"{feature_id} context zero-month share {coverage[feature_id]['zero_month_share']:.2%} > 80%")

    for feature_id in risk:
        if coverage[feature_id]["zero_month_share"] > MAX_RISK_ZERO_SHARE:
            reasons.append(f"{feature_id} risk-filter zero-month share {coverage[feature_id]['zero_month_share']:.2%} > 40%")

    common_all_core = common_months(rows, directional + risk, roles) if directional and risk else []
    if len(common_all_core) < MIN_COMMON_MONTHS:
        reasons.append(f"directional+risk common active months {len(common_all_core)} < {MIN_COMMON_MONTHS}")

    return reasons


def build_report(matrix: dict[str, Any]) -> dict[str, Any]:
    coverage = coverage_by_feature(matrix)
    rows = matrix.get("rows", [])
    roles = matrix.get("feature_roles", {})
    directional = role_feature_ids(matrix, "directional_weak_signal")
    risk = role_feature_ids(matrix, "risk_filter_candidate")
    directional_common = common_months(rows, directional, roles) if directional else []
    directional_risk_common = common_months(rows, directional + risk, roles) if directional and risk else []
    reasons = reason_codes(matrix, coverage)
    return {
        "report_type": "combo_matrix_quality_review",
        "report_date": "2026-07-13",
        "scope": "coverage_gate_not_combo_backtest",
        "ready_for_combo_hypothesis_test": not reasons,
        "allowed_next_step": "combo_hypothesis_test" if not reasons else "improve_feature_coverage_or_add_directional_features",
        "reason_codes": reasons,
        "n_months": matrix.get("n_months", 0),
        "feature_role_counts": {
            "directional_weak_signal": len(directional),
            "context_label": len(role_feature_ids(matrix, "context_label")),
            "risk_filter_candidate": len(risk),
        },
        "directional_common_active_months": directional_common,
        "directional_risk_common_active_months": directional_risk_common,
        "coverage_by_feature": coverage,
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "This is a matrix coverage gate, not a strategy test.",
            "Zero monthly value means no diagnostic event or no directional return for that feature in that month.",
            "Sparse features may remain useful for context, but not for combo hypothesis testing.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review combo matrix quality.")
    parser.add_argument("--matrix", type=Path, default=Path("reports/combo_research_matrix.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/combo_matrix_quality_review.json"))
    args = parser.parse_args(argv)

    matrix = load_json(args.matrix)
    if not matrix:
        print("ERROR: Cannot load combo research matrix")
        return 1

    report = build_report(matrix)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Ready for combo hypothesis test: {report['ready_for_combo_hypothesis_test']}")
    for reason in report["reason_codes"]:
        print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
