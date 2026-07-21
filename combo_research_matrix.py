"""Build a read-only monthly matrix for combo research diagnostics.

The matrix aligns directional weak-signal diagnostics with auxiliary context
and veto features. It is not a combo backtest and does not calculate weights.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def months_from_reports(directional: dict[str, Any], auxiliary: dict[str, Any]) -> list[str]:
    months = set()
    for table_name in ("monthly_net_return_pct_by_feature",):
        for values in directional.get(table_name, {}).values():
            months.update(values.keys())
    for table_name in ("monthly_event_counts_by_feature", "monthly_value_sums_by_feature"):
        for values in auxiliary.get(table_name, {}).values():
            months.update(values.keys())
    return sorted(months)


def feature_roles(directional: dict[str, Any], auxiliary: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for feature_id in directional.get("monthly_net_return_pct_by_feature", {}):
        roles[feature_id] = "directional_weak_signal"
    for event in auxiliary.get("events", []):
        roles[event["feature_id"]] = event["role"]
    return dict(sorted(roles.items()))


def build_rows(directional: dict[str, Any], auxiliary: dict[str, Any]) -> list[dict[str, Any]]:
    months = months_from_reports(directional, auxiliary)
    directional_returns = directional.get("monthly_net_return_pct_by_feature", {})
    aux_counts = auxiliary.get("monthly_event_counts_by_feature", {})
    aux_values = auxiliary.get("monthly_value_sums_by_feature", {})

    rows: list[dict[str, Any]] = []
    for month in months:
        row: dict[str, Any] = {"month": month}
        for feature_id, values in sorted(directional_returns.items()):
            row[f"{feature_id}__net_return_pct"] = round(float(values.get(month, 0.0)), 6)
        for feature_id, values in sorted(aux_counts.items()):
            row[f"{feature_id}__event_count"] = int(values.get(month, 0))
        for feature_id, values in sorted(aux_values.items()):
            row[f"{feature_id}__value_sum"] = round(float(values.get(month, 0.0)), 6)
        rows.append(row)
    return rows


def missing_months_by_feature(rows: list[dict[str, Any]], roles: dict[str, str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for feature_id, role in roles.items():
        if role == "directional_weak_signal":
            column = f"{feature_id}__net_return_pct"
        elif role == "risk_filter_candidate":
            column = f"{feature_id}__event_count"
        else:
            column = f"{feature_id}__event_count"
        result[feature_id] = [row["month"] for row in rows if row.get(column, 0) == 0]
    return result


def build_report(directional: dict[str, Any], auxiliary: dict[str, Any]) -> dict[str, Any]:
    rows = build_rows(directional, auxiliary)
    roles = feature_roles(directional, auxiliary)
    return {
        "report_type": "combo_research_matrix",
        "report_date": "2026-07-13",
        "scope": "monthly_alignment_diagnostics_not_combo_backtest",
        "months": [row["month"] for row in rows],
        "n_months": len(rows),
        "feature_roles": roles,
        "n_features": len(roles),
        "rows": rows,
        "missing_months_by_feature": missing_months_by_feature(rows, roles),
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "Monthly rows are for diagnostics only.",
            "Directional values are historical net-return diagnostics, not trade approvals.",
            "Auxiliary risk-filter values are event counts and veto flags, not alpha returns.",
            "No combo weights are calculated.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build combo research monthly matrix.")
    parser.add_argument("--directional", type=Path, default=Path("reports/combo_feature_timeseries.json"))
    parser.add_argument("--auxiliary", type=Path, default=Path("reports/combo_aux_feature_timeseries.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/combo_research_matrix.json"))
    args = parser.parse_args(argv)

    directional = load_json(args.directional)
    auxiliary = load_json(args.auxiliary)
    if not directional:
        print("ERROR: Cannot load directional feature time series")
        return 1
    if not auxiliary:
        print("ERROR: Cannot load auxiliary feature time series")
        return 1

    report = build_report(directional, auxiliary)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Months: {report['n_months']}")
    print(f"Features: {report['n_features']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
