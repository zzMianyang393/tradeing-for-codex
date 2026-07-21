"""Queue only mature, integrity-valid observations for later sealed evaluation."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import prospective_sealed_evaluation_spec as spec


def fingerprint_spec() -> str:
    return hashlib.sha256(inspect.getsource(spec).encode("utf-8")).hexdigest()


def build(maturity: dict, integrity: dict) -> dict:
    integrity_valid = integrity.get("integrity_status") == "valid"
    mature = [item for item in maturity.get("observations", []) if item.get("status") == "mature_awaiting_sealed_evaluation"]
    queue = [
        {key: item.get(key) for key in ("observation_id", "candidate_id", "symbol", "signal_ts", "maturity_ts")}
        for item in mature
    ] if integrity_valid else []
    readiness = spec.evidence_readiness(queue, int(maturity.get("as_of_ts", 0))) if integrity_valid else {
        "spec_version": spec.EVALUATION_SPEC_VERSION, "matured_observation_count": 0,
        "minimum_evidence_ready": False, "paper_review_ready": False, "observation_only": True,
    }
    status = "awaiting_maturity" if not mature else "blocked_integrity" if not integrity_valid else "sealed_evaluation_queue_ready"
    return {
        "report_type": "prospective_sealed_evaluation_preflight", "observation_only": True,
        "as_of_utc": maturity.get("as_of_utc"), "maturity_source_cutoff": maturity.get("source_cutoff"),
        "evaluation_spec_version": spec.EVALUATION_SPEC_VERSION, "evaluation_spec_sha256": fingerprint_spec(),
        "integrity_status": integrity.get("integrity_status"), "readiness_status": status,
        "mature_observation_count": len(mature), "queued_observation_count": len(queue), "queue": queue,
        "evidence_readiness": readiness,
        "result_evaluation_performed": False,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }


def main() -> int:
    maturity = json.loads(Path("reports/prospective_maturity_audit.json").read_text(encoding="utf-8"))
    integrity = json.loads(Path("reports/prospective_observation_integrity_audit.json").read_text(encoding="utf-8"))
    report = build(maturity, integrity)
    Path("reports/prospective_sealed_evaluation_preflight.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['readiness_status']}; queued={report['queued_observation_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
