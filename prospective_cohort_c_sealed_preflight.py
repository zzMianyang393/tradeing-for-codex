"""Prepare only mature, integrity-valid Cohort C observations for sealed review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import prospective_sealed_evaluation_spec as spec
from prospective_cohort_c_refresh_pipeline import DAY_MS, HORIZON_DAYS, identity


REPORTS = Path("reports")
FORMAL_LEDGER = REPORTS / "prospective_cohort_c_short_exploration_ledger.json"
FORMAL_REGISTRY = REPORTS / "prospective_cohort_c_observation_registry.json"
FORMAL_MATURITY = REPORTS / "prospective_cohort_c_maturity_audit.json"
OUTPUT = REPORTS / "prospective_cohort_c_sealed_evaluation_preflight.json"


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def audit_integrity(ledger: dict[str, Any], registry: dict[str, Any], maturity: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    signals = ledger.get("signals", [])
    observations = registry.get("observations", [])
    if ledger.get("signal_count") != registry.get("registry_signal_count"):
        issues.append("Ledger and registry signal counts differ.")
    expected_by_id = {identity(signal): signal for signal in signals}
    seen: set[str] = set()
    for observation in observations:
        observation_id = observation.get("observation_id", "")
        signal = expected_by_id.get(observation_id)
        if not signal:
            issues.append(f"Unknown observation identity: {observation_id}")
            continue
        if observation_id in seen:
            issues.append(f"Duplicate observation identity: {observation_id}")
        seen.add(observation_id)
        if observation.get("maturity_ts") != int(signal["signal_ts"]) + HORIZON_DAYS * DAY_MS:
            issues.append(f"Maturity mismatch: {observation_id}")
    if set(expected_by_id) != seen:
        issues.append("Ledger and registry identities differ.")
    if maturity.get("as_of_utc", "") > ledger.get("common_data_cutoff", ""):
        issues.append("Maturity cutoff exceeds the formal ledger cutoff.")
    return {
        "integrity_status": "valid" if not issues else "invalid",
        "n_issues": len(issues),
        "issues": issues,
        "observation_only": True,
    }


def build(ledger: dict[str, Any] | None, registry: dict[str, Any] | None, maturity: dict[str, Any] | None) -> dict[str, Any]:
    gates = {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}
    if not ledger or not registry or not maturity:
        return {
            "report_type": "prospective_cohort_c_sealed_evaluation_preflight",
            "observation_only": True,
            "readiness_status": "awaiting_first_published_observation",
            "formal_artifacts_available": False,
            "integrity": {"integrity_status": "not_applicable", "n_issues": 0, "issues": []},
            "mature_observation_count": 0,
            "queued_observation_count": 0,
            "queue": [],
            "result_evaluation_performed": False,
            "safety_gates": gates,
        }
    integrity = audit_integrity(ledger, registry, maturity)
    mature = [row for row in maturity.get("observations", []) if row.get("status") == "mature_awaiting_sealed_evaluation"]
    queue = [{key: row.get(key) for key in ("observation_id", "hypothesis_id", "symbol", "signal_ts", "maturity_ts")} for row in mature] if integrity["integrity_status"] == "valid" else []
    readiness = spec.evidence_readiness(queue, int(maturity.get("as_of_ts", 0))) if integrity["integrity_status"] == "valid" else {
        "spec_version": spec.EVALUATION_SPEC_VERSION, "matured_observation_count": 0,
        "minimum_evidence_ready": False, "paper_review_ready": False, "observation_only": True,
    }
    status = "awaiting_maturity" if not mature else "blocked_integrity" if integrity["integrity_status"] != "valid" else "sealed_evaluation_queue_ready"
    return {
        "report_type": "prospective_cohort_c_sealed_evaluation_preflight",
        "observation_only": True,
        "readiness_status": status,
        "formal_artifacts_available": True,
        "as_of_utc": maturity.get("as_of_utc"),
        "integrity": integrity,
        "mature_observation_count": len(mature),
        "queued_observation_count": len(queue),
        "queue": queue,
        "evidence_readiness": readiness,
        "result_evaluation_performed": False,
        "safety_gates": gates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight Cohort C sealed evaluation.")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    report = build(load_json(FORMAL_LEDGER), load_json(FORMAL_REGISTRY), load_json(FORMAL_MATURITY))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['readiness_status']}; queued={report['queued_observation_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
