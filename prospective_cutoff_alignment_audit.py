"""Read-only alignment audit for the active prospective cohorts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPORTS = Path("reports")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build(data_quality: dict[str, Any], cohort_b: dict[str, Any], cohort_c: dict[str, Any]) -> dict[str, Any]:
    expected = str(data_quality.get("common_cutoff_utc", ""))
    observed = {
        "cohort_b": str(cohort_b.get("source_cutoffs", {}).get("combined", "")),
        "cohort_c": str(cohort_c.get("common_data_cutoff", "")),
    }
    issues = [f"{name} cutoff {cutoff or 'missing'} != data quality cutoff {expected or 'missing'}"
              for name, cutoff in observed.items() if not expected or cutoff != expected]
    return {
        "audit_type": "prospective_cutoff_alignment",
        "observation_only": True,
        "data_quality_cutoff": expected,
        "active_cohort_cutoffs": observed,
        "cohort_a_excluded_reason": "sealed cohort uses its immutable genesis cutoff",
        "alignment_status": "valid" if not issues else "invalid",
        "issues": issues,
        "outcomes_evaluated": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def main() -> int:
    report = build(
        load_json(REPORTS / "data_quality_audit.json"),
        load_json(REPORTS / "cohort_b_signal_only_refresh.json"),
        load_json(REPORTS / "cohort_c_refresh_pipeline.json"),
    )
    (REPORTS / "prospective_cutoff_alignment_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"alignment={report['alignment_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
