"""Provenance gate for auxiliary features before prospective attachment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FEATURE_SOURCES = {
    "feat_funding_term_carry": {
        "path": "reports/funding_term_carry_audit.json",
        "role": "context_label",
        "availability_contract": "rebuild rolling funding from raw history before any prospective use",
    },
    "feat_daily_low_turnover_momentum": {
        "path": "reports/daily_low_turnover_momentum_audit.json",
        "role": "context_label",
        "availability_contract": "rebuild momentum state from completed daily bars before any prospective use",
    },
    "feat_daily_ma_alignment": {
        "path": "reports/daily_ma_alignment_audit.json",
        "role": "context_label",
        "availability_contract": "rebuild alignment state from completed daily bars before any prospective use",
    },
    "feat_daily_oi_independent_change": {
        "path": "reports/daily_oi_independent_change_audit.json",
        "role": "risk_filter_candidate",
        "availability_contract": "rebuild from raw daily OI; earliest prospective availability is 16:15 UTC",
    },
    "feat_range_regime_mean_reversion_family": {
        "path": "reports/range_regime_mean_reversion_audit.json",
        "role": "risk_filter_candidate",
        "availability_contract": "rebuild range-risk state from completed 4h inputs before any prospective use",
    },
}

OUTCOME_OR_EXECUTION_FRAGMENTS = (
    "return",
    "exit",
    "entry",
    "price",
    "hold",
    "profit",
    "pnl",
    "win",
    "loss",
)
TIME_FIELD_NAMES = {"signal_ts", "event_ts", "timestamp_utc"}


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def classify_source(feature_id: str, source: dict[str, str], report: dict[str, Any] | None) -> dict[str, Any]:
    events = report.get("events", []) if report else []
    field_names = {str(key).lower() for event in events if isinstance(event, dict) for key in event}
    contaminated = any(fragment in field for field in field_names for fragment in OUTCOME_OR_EXECUTION_FRAGMENTS)
    has_event_time = bool(field_names & TIME_FIELD_NAMES)
    if not report or not events:
        status = "source_unavailable"
    elif contaminated:
        status = "outcome_tainted_rebuild_from_raw_required"
    elif not has_event_time:
        status = "missing_available_time_rebuild_from_raw_required"
    else:
        status = "raw_rebuild_candidate"
    return {
        "feature_id": feature_id,
        "role": source["role"],
        "source_path": source["path"],
        "source_event_count": len(events),
        "source_contains_outcome_or_execution_fields": contaminated,
        "source_has_event_time": has_event_time,
        "provenance_status": status,
        "forward_attach_allowed": False,
        "availability_contract": source["availability_contract"],
    }


def build_report(base_dir: Path = Path(".")) -> dict[str, Any]:
    features = []
    for feature_id, source in FEATURE_SOURCES.items():
        report = load_json(base_dir / source["path"])
        features.append(classify_source(feature_id, source, report))
    counts: dict[str, int] = {}
    for feature in features:
        status = feature["provenance_status"]
        counts[status] = counts.get(status, 0) + 1
    return {
        "report_type": "prospective_auxiliary_feature_admission",
        "observation_only": True,
        "feature_count": len(features),
        "status_counts": dict(sorted(counts.items())),
        "features": features,
        "admitted_for_forward_attachment": [],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "Historical audit event series are not automatically prospective inputs.",
            "Any outcome- or execution-tainted source must be rebuilt from raw contemporaneously available inputs.",
            "Risk filters remain veto-only after a future raw-data rebuild.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit auxiliary-feature provenance for prospective research.")
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_auxiliary_feature_admission.json"))
    args = parser.parse_args(argv)
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Forward attachments admitted: {len(report['admitted_for_forward_attachment'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
