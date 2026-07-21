"""Read-only readiness gate for a scheduled Cohort B observational candidate."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_utc(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def build(activation: dict, data_quality: dict, overlap: dict, checkpoint: dict, generator: dict | None = None) -> dict:
    record = activation["activation_records"][0]
    cutoff = data_quality["common_cutoff_utc"]
    cutoff_ts, not_before = parse_utc(cutoff), int(record["not_before_signal_ts"])
    overlap_complete = overlap.get("conclusion") in {"no_same_day_overlap_observed", "overlap_penalty_required_before_any_combo_research"}
    generator_available = bool((generator or {}).get("generator_available"))
    data_ready = cutoff_ts >= not_before
    status = "ready_for_signal_only_generation" if data_ready and overlap_complete and generator_available else "awaiting_common_data_cutoff" if not data_ready else "awaiting_overlap_audit" if not overlap_complete else "awaiting_generator"
    return {
        "audit_type": "cohort_b_activation_readiness", "observation_only": True,
        "candidate_id": record["candidate_id"], "common_data_cutoff": cutoff,
        "not_before_signal_utc": record["not_before_signal_utc"], "data_ready": data_ready,
        "overlap_audit_complete": overlap_complete, "generator_available": generator_available, "readiness_status": status,
        "eligible_to_generate_observation": data_ready and overlap_complete and generator_available,
        "reason": "All observation-only generator gates are satisfied." if status == "ready_for_signal_only_generation" else "Common data cutoff is before the frozen non-backfill activation boundary." if not data_ready else "Overlap audit is incomplete." if not overlap_complete else "Signal-only generator is not available.",
        "checkpoint_count": checkpoint.get("current_count", 0),
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }


def main() -> int:
    report = build(load(Path("reports/cohort_b_candidate_activation_registry.json")), load(Path("reports/data_quality_audit.json")), load(Path("reports/volatility_expansion_volume_shock_overlap_audit.json")), load(Path("reports/prospective_cohort_b_observation_checkpoint.json")), load(Path("reports/prospective_cohort_b_volatility_expansion_staging_ledger.json")))
    output = Path("reports/cohort_b_activation_readiness_audit.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["readiness_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
