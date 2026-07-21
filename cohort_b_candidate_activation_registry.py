"""Freeze non-backfill activation boundaries for qualified Cohort B candidates."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

DAY_MS = 24 * 3600 * 1000
VOLATILITY_RULE_ID = "daily_volatility_expansion_continuation_v1"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def next_daily_open_after(ts: int) -> int:
    return ((ts // DAY_MS) + 1) * DAY_MS


def fingerprint(report: dict) -> str:
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build(checkpoint: dict, volatility_audit: dict) -> dict:
    if volatility_audit.get("status") != "historical_research_candidate":
        raise ValueError("Only a historically qualified candidate may receive an activation boundary")
    max_existing_signal_ts = int(checkpoint.get("max_signal_ts", 0))
    not_before = next_daily_open_after(max_existing_signal_ts)
    return {
        "registry_type": "cohort_b_candidate_activation_registry",
        "cohort_id": checkpoint.get("cohort_id"),
        "observation_only": True,
        "activation_records": [{
            "candidate_id": VOLATILITY_RULE_ID,
            "audit_report": "reports/daily_volatility_expansion_continuation_audit.json",
            "audit_fingerprint_sha256": fingerprint(volatility_audit),
            "historical_status": volatility_audit["status"],
            "existing_checkpoint_max_signal_ts": max_existing_signal_ts,
            "not_before_signal_ts": not_before,
            "not_before_signal_utc": datetime.fromtimestamp(not_before / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "activation_status": "signal_only_generator_enabled",
            "remaining_requirements": [
                "new signal timestamp must be strictly later than the published Cohort B checkpoint maximum",
                "generated observations require their own sealed maturity evaluation before any later research decision",
                "signal-only generation does not create paper or trading eligibility",
            ],
        }],
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }


def main() -> int:
    checkpoint = load_json(Path("reports/prospective_cohort_b_observation_checkpoint.json"))
    audit = load_json(Path("reports/daily_volatility_expansion_continuation_audit.json"))
    report = build(checkpoint, audit)
    output = Path("reports/cohort_b_candidate_activation_registry.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["activation_records"][0]["not_before_signal_utc"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
