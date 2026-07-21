"""Prospective refresh publish audit: verify post-publish consistency.

Verifies:
  - Genesis baseline identities unchanged (per-record)
  - Rolling checkpoint lost no observations
  - Ledger, registry, maturity, integrity, checkpoint counts consistent
  - Current cutoff >= genesis cutoff (monotonic)
  - Safety gates still closed
  - No result fields

This is a READ-ONLY audit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FORBIDDEN_KEYS = {
    "pnl", "return", "returns", "price", "entry_price", "exit_price",
    "position", "order", "trade", "win", "loss", "mfe", "mae",
}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _collect_keys(obj) -> set[str]:
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k.lower())
            keys |= _collect_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _collect_keys(item)
    return keys


def audit_publish(
    checkpoint: dict | None,
    ledger: dict | None,
    registry: dict | None,
    maturity: dict | None,
    integrity: dict | None,
) -> dict:
    """Audit post-publish consistency."""
    issues: list[str] = []

    # 1. Checkpoint exists
    if not checkpoint:
        issues.append("Checkpoint missing")
        return {"integrity_status": "invalid", "n_issues": len(issues), "issues": issues}

    # 2. Genesis baseline per-record verification
    genesis_ids = checkpoint.get("genesis_identities", {})
    current_ids = checkpoint.get("identities", {})
    for oid, gen_obs in genesis_ids.items():
        cur_obs = current_ids.get(oid)
        if cur_obs is None:
            issues.append(f"Genesis identity {oid} missing from current identities")
        else:
            for field in ["candidate_id", "signal_ts", "symbol", "direction", "regime", "maturity_ts"]:
                if cur_obs.get(field) != gen_obs.get(field):
                    issues.append(f"Genesis identity {oid}: field '{field}' changed")

    # 3. Genesis count preserved
    genesis_count = checkpoint.get("genesis_count", 0)
    current_count = checkpoint.get("current_count", 0)
    if current_count < genesis_count:
        issues.append(f"Checkpoint lost observations: genesis={genesis_count}, current={current_count}")
    if len(genesis_ids) != genesis_count:
        issues.append(f"Genesis identities count mismatch: {len(genesis_ids)} vs genesis_count={genesis_count}")

    # 4. 5-way count consistency
    ledger_count = ledger.get("signal_count", 0) if ledger else 0
    registry_count = registry.get("registry_signal_count", 0) if registry else 0
    maturity_count = maturity.get("n_observations", 0) if maturity else 0
    integrity_count = integrity.get("cross_check", {}).get("registry_signal_count", 0) if integrity else 0
    checkpoint_count = checkpoint.get("current_count", 0)

    counts = {
        "ledger": ledger_count,
        "registry": registry_count,
        "maturity": maturity_count,
        "integrity": integrity_count,
        "checkpoint": checkpoint_count,
    }
    unique_counts = set(counts.values())
    if len(unique_counts) > 1:
        issues.append(f"Signal counts inconsistent: {counts}")

    # 5. Cutoff monotonicity
    genesis_cutoff = checkpoint.get("genesis_cutoff", "")
    current_cutoff = checkpoint.get("current_cutoff", "")
    if genesis_cutoff and current_cutoff and current_cutoff < genesis_cutoff:
        issues.append(f"Cutoff regressed: current={current_cutoff} < genesis={genesis_cutoff}")

    # 6. Safety gates
    if maturity:
        gates = maturity.get("safety_gates", {})
        if gates.get("approved_for_paper") != []:
            issues.append("approved_for_paper not empty")
        if gates.get("safe_to_enable_trading") is not False:
            issues.append("safe_to_enable_trading not false")

    # 7. No result fields in reports
    for name, report in [("ledger", ledger), ("registry", registry), ("maturity", maturity)]:
        if report:
            keys = _collect_keys(report)
            found = keys & FORBIDDEN_KEYS
            if found:
                issues.append(f"{name} contains forbidden keys: {found}")

    # 8. Integrity audit valid
    if integrity and integrity.get("integrity_status") != "valid":
        issues.append("Integrity audit not valid")

    return {
        "audit_type": "prospective_refresh_publish_audit",
        "audit_date": "2026-07-14",
        "observation_only": True,
        "integrity_status": "valid" if not issues else "invalid",
        "n_issues": len(issues),
        "issues": issues,
        "counts": counts,
        "genesis_count": genesis_count,
        "current_count": current_count,
        "genesis_cutoff": genesis_cutoff,
        "current_cutoff": current_cutoff,
        "cutoff_monotonic": current_cutoff >= genesis_cutoff if genesis_cutoff and current_cutoff else True,
        "genesis_identities_verified": len(genesis_ids),
        "genesis_identities_preserved": sum(
            1 for oid in genesis_ids if oid in current_ids
        ),
        "methodology_notes": [
            "Cross-validates checkpoint, ledger, registry, maturity, integrity.",
            "Verifies per-record genesis baseline preservation.",
            "Verifies 5-way count consistency.",
            "Verifies cutoff monotonicity.",
            "No returns or PnL calculated.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Prospective refresh publish audit.")
    p.add_argument("--checkpoint", type=Path, default=Path("reports/prospective_observation_checkpoint.json"))
    p.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    p.add_argument("--registry", type=Path, default=Path("reports/prospective_observation_registry.json"))
    p.add_argument("--maturity", type=Path, default=Path("reports/prospective_maturity_audit.json"))
    p.add_argument("--integrity", type=Path, default=Path("reports/prospective_observation_integrity_audit.json"))
    p.add_argument("--out", type=Path, default=Path("reports/prospective_refresh_publish_audit.json"))
    args = p.parse_args(argv)

    result = audit_publish(
        load_json(args.checkpoint),
        load_json(args.ledger),
        load_json(args.registry),
        load_json(args.maturity),
        load_json(args.integrity),
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Integrity: {result['integrity_status']} ({result['n_issues']} issues)")
    for issue in result["issues"]:
        print(f"  - {issue}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
