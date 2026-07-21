"""Prospective observation integrity audit: cross-validate ledger, registry, and maturity.

Detects:
  - Signal count mismatches
  - observation_id inconsistencies
  - Identity hash changes
  - maturity_ts calculation errors
  - Duplicate identities
  - Cutoff violations

This is a READ-ONLY audit.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from prospective_observation_registry import OBSERVATION_HORIZON_DAYS, DAY_MS, compute_identity_hash


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def audit_integrity(
    ledger: dict,
    registry: dict,
    maturity: dict | None,
) -> dict:
    """Cross-validate ledger, registry, and maturity audit."""
    issues: list[str] = []

    ledger_count = ledger.get("signal_count", 0)
    registry_count = registry.get("registry_signal_count", 0)
    cutoff = ledger.get("common_data_cutoff", "")

    # 1. Signal count match
    if ledger_count != registry_count:
        issues.append(f"Signal count mismatch: ledger={ledger_count}, registry={registry_count}")

    # 2. Per-signal validation
    ledger_signals = ledger.get("signals", [])
    registry_obs = registry.get("observations", [])

    # Build lookup by index
    for i, (sig, obs) in enumerate(zip(ledger_signals, registry_obs)):
        # observation_id consistency
        expected_hash = compute_identity_hash(
            sig.get("candidate_id", ""),
            sig.get("rule_version", ""),
            sig.get("signal_ts", 0),
            sig.get("symbol", ""),
            sig.get("direction", ""),
            sig.get("regime", ""),
        )
        if obs.get("observation_id") != expected_hash:
            issues.append(f"Signal {i}: identity hash mismatch")

        # maturity_ts correctness
        expected_maturity = sig.get("signal_ts", 0) + OBSERVATION_HORIZON_DAYS * DAY_MS
        if obs.get("maturity_ts") != expected_maturity:
            issues.append(f"Signal {i}: maturity_ts mismatch (expected {expected_maturity}, got {obs.get('maturity_ts')})")

        # Duplicate check
        if obs.get("duplicate_identity"):
            issues.append(f"Signal {i}: duplicate identity '{obs.get('observation_id')}'")

    # 3. Cutoff check
    if maturity:
        mat_cutoff = maturity.get("as_of_utc", "")
        if mat_cutoff > cutoff:
            issues.append(f"Maturity audit cutoff ({mat_cutoff}) > ledger cutoff ({cutoff})")

    # 4. Hash uniqueness
    hashes = [obs.get("observation_id") for obs in registry_obs]
    if len(hashes) != len(set(hashes)):
        dup_hashes = [h for h in hashes if hashes.count(h) > 1]
        issues.append(f"Duplicate hashes found: {set(dup_hashes)}")

    integrity_status = "valid" if not issues else "invalid"

    return {
        "audit_type": "prospective_observation_integrity",
        "audit_date": "2026-07-14",
        "observation_only": True,
        "integrity_status": integrity_status,
        "n_issues": len(issues),
        "issues": issues,
        "cross_check": {
            "ledger_signal_count": ledger_count,
            "registry_signal_count": registry_count,
            "counts_match": ledger_count == registry_count,
            "common_data_cutoff": cutoff,
            "maturity_as_of": maturity.get("as_of_utc") if maturity else None,
        },
        "methodology_notes": [
            "Cross-validates ledger, registry, and maturity audit.",
            "Checks signal count, identity hash, maturity_ts, duplicates, cutoff.",
            "No returns or PnL calculated.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Prospective observation integrity audit.")
    p.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    p.add_argument("--registry", type=Path, default=Path("reports/prospective_observation_registry.json"))
    p.add_argument("--maturity", type=Path, default=Path("reports/prospective_maturity_audit.json"))
    p.add_argument("--out", type=Path, default=Path("reports/prospective_observation_integrity_audit.json"))
    args = p.parse_args(argv)

    ledger = load_json(args.ledger)
    registry = load_json(args.registry)
    maturity = load_json(args.maturity)

    if not ledger or not registry:
        print("ERROR: Cannot load ledger or registry")
        return 1

    result = audit_integrity(ledger, registry, maturity)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Integrity: {result['integrity_status']} ({result['n_issues']} issues)")
    for issue in result["issues"]:
        print(f"  - {issue}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
