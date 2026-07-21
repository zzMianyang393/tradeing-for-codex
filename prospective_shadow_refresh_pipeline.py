"""Prospective shadow refresh pipeline: append-only ledger refresh.

Pipeline stages:
  1. Generate staging ledger (written to STAGING_LEDGER)
  2. Generate staging registry, maturity, integrity from staging ledger
  3. Append-only validation against checkpoint
  4. Decision: no_changes / ready_to_commit / rejected
  5. Atomic publish (only --commit with new_observations > 0 and all valid)

Default mode: dry-run (no publish, no production file modification).

This module does NOT:
  - Calculate returns, PnL, or prices
  - Read market data after the checkpoint cutoff
  - Modify existing observations
  - Import runner.py
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from prospective_observation_registry import (
    build_registry,
    load_ledger,
    compute_identity_hash,
    OBSERVATION_HORIZON_DAYS,
    DAY_MS,
)
from prospective_maturity_audit import audit_maturity
from prospective_observation_integrity_audit import audit_integrity


REPORTS = Path("reports")
STAGING = REPORTS / "staging"

LEDGER_PATH = REPORTS / "prospective_shadow_signal_ledger.json"
REGISTRY_PATH = REPORTS / "prospective_observation_registry.json"
MATURITY_PATH = REPORTS / "prospective_maturity_audit.json"
INTEGRITY_PATH = REPORTS / "prospective_observation_integrity_audit.json"
CHECKPOINT_PATH = REPORTS / "prospective_observation_checkpoint.json"

STAGING_LEDGER = STAGING / "prospective_shadow_signal_ledger.json"
STAGING_REGISTRY = STAGING / "prospective_observation_registry.json"
STAGING_MATURITY = STAGING / "prospective_maturity_audit.json"
STAGING_INTEGRITY = STAGING / "prospective_observation_integrity_audit.json"

PUBLISH_FILES = [
    (STAGING_LEDGER, LEDGER_PATH),
    (STAGING_REGISTRY, REGISTRY_PATH),
    (STAGING_MATURITY, MATURITY_PATH),
    (STAGING_INTEGRITY, INTEGRITY_PATH),
]


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_checkpoint_from_registry(registry: dict, genesis: dict | None = None) -> dict:
    """Build checkpoint, preserving genesis baseline if provided."""
    observations = registry.get("observations", [])
    identities = {}
    for obs in observations:
        oid = obs["observation_id"]
        identities[oid] = {
            "observation_id": oid,
            "candidate_id": obs["candidate_id"],
            "signal_ts": obs["signal_ts"],
            "symbol": obs["symbol"],
            "direction": obs["direction"],
            "regime": obs["regime"],
            "maturity_ts": obs["maturity_ts"],
        }

    max_signal_ts = max((obs["signal_ts"] for obs in observations), default=0)
    cutoff_str = registry.get("common_data_cutoff", "")

    # Preserve genesis baseline
    genesis_count = genesis.get("genesis_count", len(observations)) if genesis else len(observations)
    genesis_identities = genesis.get("genesis_identities", identities) if genesis else identities
    genesis_cutoff = genesis.get("genesis_cutoff", cutoff_str) if genesis else cutoff_str

    return {
        "checkpoint_type": "prospective_observation_checkpoint",
        "version": "1.0.0",
        "created_from": "initial_28_observations",
        "genesis_count": genesis_count,
        "genesis_cutoff": genesis_cutoff,
        "genesis_identities": genesis_identities,
        "current_count": len(observations),
        "current_cutoff": cutoff_str,
        "max_signal_ts": max_signal_ts,
        "max_signal_utc": datetime.fromtimestamp(
            max_signal_ts / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S") if max_signal_ts else None,
        "identities": identities,
    }


def validate_append_only(
    checkpoint: dict,
    staging_registry: dict,
) -> dict:
    """Validate that staging only appends new observations."""
    issues: list[str] = []

    checkpoint_ids = set(checkpoint.get("identities", {}).keys())
    staging_obs = staging_registry.get("observations", [])
    staging_ids = {obs["observation_id"] for obs in staging_obs}

    # 1. All checkpoint observations must still exist unchanged
    for oid, cp_obs in checkpoint.get("identities", {}).items():
        staging_match = next((o for o in staging_obs if o["observation_id"] == oid), None)
        if staging_match is None:
            issues.append(f"Checkpoint observation {oid} missing from staging")
        else:
            for field in ["candidate_id", "signal_ts", "symbol", "direction", "regime", "maturity_ts"]:
                if staging_match.get(field) != cp_obs.get(field):
                    issues.append(f"Observation {oid}: field '{field}' changed")

    # 2. New observations must have signal_ts > checkpoint max_signal_ts
    cp_max_ts = checkpoint.get("max_signal_ts", 0)
    new_ids = staging_ids - checkpoint_ids
    for obs in staging_obs:
        if obs["observation_id"] in new_ids:
            if obs["signal_ts"] <= cp_max_ts:
                issues.append(
                    f"New observation {obs['observation_id']}: "
                    f"signal_ts={obs['signal_ts']} <= checkpoint max={cp_max_ts}"
                )

    # 3. No duplicates
    if len(staging_ids) != len(staging_obs):
        issues.append("Duplicate observation_ids in staging")

    # 4. Identity hash consistency
    for obs in staging_obs:
        expected_hash = compute_identity_hash(
            obs["candidate_id"], obs.get("rule_version", ""),
            obs["signal_ts"], obs["symbol"], obs["direction"], obs["regime"],
        )
        if obs["observation_id"] != expected_hash:
            issues.append(f"Observation {obs['observation_id']}: hash mismatch")

    # 5. Cutoff must not regress
    staging_cutoff = staging_registry.get("common_data_cutoff", "")
    cp_cutoff = checkpoint.get("current_cutoff", "")
    if staging_cutoff and cp_cutoff and staging_cutoff < cp_cutoff:
        issues.append(f"Cutoff regressed: staging={staging_cutoff} < checkpoint={cp_cutoff}")

    valid = len(issues) == 0
    return {
        "valid": valid,
        "n_issues": len(issues),
        "issues": issues,
        "checkpoint_count": len(checkpoint_ids),
        "staging_count": len(staging_obs),
        "new_count": len(new_ids),
        "removed_count": len(checkpoint_ids - staging_ids),
    }


def transactional_publish_with_rollback(
    staging_to_prod: list[tuple[Path, Path]],
    checkpoint_data: dict,
    _fail_at: int | None = None,
) -> dict:
    """Transactional publish with rollback on failure.

    1. Back up all existing production files to same-dir .bak files.
    2. Write all staging + checkpoint to same-dir .tmp files.
    3. Replace each production file via os.replace.
    4. On any failure: restore backups, delete newly created files,
       verify byte-for-byte match with pre-publish state.

    _fail_at: for testing only — simulate failure at 0-indexed replace step.
    """
    checkpoint_path = CHECKPOINT_PATH

    # Build full list: staging pairs + checkpoint
    all_pairs = list(staging_to_prod)
    checkpoint_tmp: Path | None = None
    backup_files: list[tuple[Path, Path]] = []  # (original, backup)
    tmp_files: list[Path] = []
    replaced: list[tuple[Path, Path]] = []  # (tmp, dst) — successfully replaced
    newly_created: list[Path] = []  # dst files that didn't exist before

    try:
        # Phase 1: Back up existing production files
        for _, dst in all_pairs:
            if dst.exists():
                bak = dst.with_suffix(dst.suffix + ".bak")
                bak.write_bytes(dst.read_bytes())
                backup_files.append((dst, bak))

        if checkpoint_path.exists():
            bak = checkpoint_path.with_suffix(checkpoint_path.suffix + ".bak")
            bak.write_bytes(checkpoint_path.read_bytes())
            backup_files.append((checkpoint_path, bak))

        # Phase 2: Write all staging to temp files
        for src, dst in all_pairs:
            if not src.exists():
                raise FileNotFoundError(f"Staging file missing: {src}")
            tmp_fd, tmp_path = tempfile.mkstemp(dir=str(dst.parent), suffix=".tmp")
            os.close(tmp_fd)
            tmp = Path(tmp_path)
            tmp.write_bytes(src.read_bytes())
            tmp_files.append(tmp)
            if not dst.exists():
                newly_created.append(dst)

        # Write checkpoint to temp
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(checkpoint_path.parent), suffix=".tmp")
        os.close(tmp_fd)
        checkpoint_tmp = Path(tmp_path)
        checkpoint_tmp.write_text(
            json.dumps(checkpoint_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp_files.append(checkpoint_tmp)
        if not checkpoint_path.exists():
            newly_created.append(checkpoint_path)

        # Phase 3: Replace each file
        all_replacements = [(tmp_files[i], all_pairs[i][1]) for i in range(len(all_pairs))]
        all_replacements.append((checkpoint_tmp, checkpoint_path))

        for step_idx, (tmp, dst) in enumerate(all_replacements):
            # Fault injection for testing
            if _fail_at is not None and step_idx == _fail_at:
                raise OSError(f"Injected failure at step {step_idx}")

            os.replace(str(tmp), str(dst))
            replaced.append((tmp, dst))
            if tmp in tmp_files:
                tmp_files.remove(tmp)

        # Phase 4: Verify all 5 files exist
        all_dsts = [dst for _, dst in all_pairs] + [checkpoint_path]
        for dst in all_dsts:
            if not dst.exists():
                raise FileNotFoundError(f"Post-publish verification failed: {dst} missing")

        return {
            "success": True,
            "published": [str(dst) for _, dst in replaced],
            "rollback_attempted": False,
            "rollback_succeeded": None,
        }

    except Exception as e:
        # Rollback: restore backups, clean up newly created files
        rollback_attempted = True
        rollback_ok = True

        # Restore backed-up files
        for original, bak in backup_files:
            try:
                if bak.exists():
                    os.replace(str(bak), str(original))
            except OSError:
                rollback_ok = False

        # Delete newly created files that didn't exist before
        for dst in newly_created:
            try:
                if dst.exists():
                    dst.unlink()
            except OSError:
                rollback_ok = False

        # Clean up remaining temp files
        for tmp in tmp_files:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

        # Verify byte-for-byte match with pre-publish state
        for original, bak in backup_files:
            if original.exists() and bak.exists():
                if original.read_bytes() != bak.read_bytes():
                    rollback_ok = False

        # Clean up backup files after verification
        for _, bak in backup_files:
            try:
                bak.unlink(missing_ok=True)
            except OSError:
                pass

        return {
            "success": False,
            "error": str(e),
            "published": [str(dst) for _, dst in replaced],
            "rollback_attempted": rollback_attempted,
            "rollback_succeeded": rollback_ok,
        }


def run_pipeline(
    staging_ledger_path: Path | None = None,
    commit: bool = False,
) -> dict:
    """Run the refresh pipeline."""

    # Load checkpoint (or create from current registry)
    checkpoint = load_json(CHECKPOINT_PATH)
    if checkpoint is None:
        registry = load_json(REGISTRY_PATH)
        if not registry:
            return {"status": "error", "reason": "Cannot load registry to build checkpoint"}
        checkpoint = build_checkpoint_from_registry(registry)
        save_json(CHECKPOINT_PATH, checkpoint)

    # Load source ledger
    source_ledger = load_json(staging_ledger_path or LEDGER_PATH)
    if not source_ledger:
        return {"status": "error", "reason": "Cannot load source ledger"}

    # Stage 1: Write staging ledger
    save_json(STAGING_LEDGER, source_ledger)

    # Stage 2: Generate staging registry from staging ledger
    staging_registry = build_registry(source_ledger)
    # Pass cutoff from ledger into registry for audit
    staging_registry["common_data_cutoff"] = source_ledger.get("common_data_cutoff", "")
    save_json(STAGING_REGISTRY, staging_registry)

    # Stage 3: Generate staging maturity audit
    cutoff_str = source_ledger.get("common_data_cutoff", "")
    cutoff_ts = int(
        datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc).timestamp() * 1000
    )
    staging_maturity = audit_maturity(staging_registry, cutoff_ts)
    save_json(STAGING_MATURITY, staging_maturity)

    # Stage 4: Generate staging integrity audit
    staging_integrity = audit_integrity(source_ledger, staging_registry, staging_maturity)
    save_json(STAGING_INTEGRITY, staging_integrity)

    # Stage 5: Append-only validation
    append_result = validate_append_only(checkpoint, staging_registry)

    # Decision
    integrity_valid = staging_integrity.get("integrity_status") == "valid"
    append_valid = append_result.get("valid", False)
    new_count = append_result.get("new_count", 0)

    if not append_valid or not integrity_valid:
        decision = "rejected"
    elif new_count == 0:
        decision = "no_changes"
    else:
        decision = "ready_to_commit"

    result = {
        "pipeline_type": "prospective_shadow_refresh",
        "run_date": "2026-07-14",
        "observation_only": True,
        "mode": "commit" if commit else "dry_run",
        "refresh_decision": decision,
        "append_validation": append_result,
        "integrity_status": staging_integrity.get("integrity_status"),
        "staging_signal_count": staging_registry.get("registry_signal_count", 0),
        "checkpoint_signal_count": checkpoint.get("current_count", 0),
        "new_observations": new_count,
        "methodology_notes": [
            "Default mode is dry-run. Only --commit with new_observations > 0 allows publish.",
            "Same data produces no_changes, not ready_to_commit.",
            "Append-only: existing observations cannot be modified or removed.",
            "Atomic publish: temp files + os.replace. Failure preserves old files.",
            "No returns, PnL, or prices calculated.",
        ],
    }

    # Publish only if commit, valid, and new observations exist
    if commit and decision == "ready_to_commit":
        # Build new checkpoint preserving genesis
        genesis = {
            "genesis_count": checkpoint.get("genesis_count", 28),
            "genesis_identities": checkpoint.get("genesis_identities", {}),
            "genesis_cutoff": checkpoint.get("genesis_cutoff", ""),
        }
        new_checkpoint = build_checkpoint_from_registry(staging_registry, genesis)

        # Also add staging registry cutoff for publish audit
        staging_registry["common_data_cutoff"] = source_ledger.get("common_data_cutoff", "")

        pub_result = transactional_publish_with_rollback(PUBLISH_FILES, new_checkpoint)
        result["published"] = pub_result["success"]
        result["publish_detail"] = pub_result
        if not pub_result["success"]:
            result["reject_reasons"] = [f"Transactional publish failed: {pub_result.get('error')}"]
    else:
        result["published"] = False
        if decision == "rejected":
            result["reject_reasons"] = append_result.get("issues", []) + (
                ["Integrity check failed"] if not integrity_valid else []
            )
        elif decision == "no_changes":
            result["reject_reasons"] = ["No new observations to commit"]

    # Save pipeline report (this is always allowed, even in dry-run)
    save_json(REPORTS / "prospective_shadow_refresh_pipeline.json", result)

    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Prospective shadow refresh pipeline.")
    p.add_argument("--staging-ledger", type=Path, default=None, help="Path to staging ledger")
    p.add_argument("--commit", action="store_true", help="Publish (only if all validations pass)")
    p.add_argument("--init-checkpoint", action="store_true", help="Initialize checkpoint from current registry")
    p.add_argument("--out", type=Path, default=Path("reports/prospective_shadow_refresh_pipeline.json"))
    args = p.parse_args(argv)

    if args.init_checkpoint:
        registry = load_json(REGISTRY_PATH)
        if not registry:
            print("ERROR: Cannot load registry")
            return 1
        checkpoint = build_checkpoint_from_registry(registry)
        save_json(CHECKPOINT_PATH, checkpoint)
        print(f"Checkpoint initialized: {checkpoint['current_count']} observations")
        return 0

    result = run_pipeline(args.staging_ledger, args.commit)

    print(f"Decision: {result['refresh_decision']}")
    print(f"Mode: {result['mode']}")
    print(f"Staging signals: {result['staging_signal_count']}")
    print(f"New observations: {result['new_observations']}")
    print(f"Published: {result.get('published', False)}")

    if result.get("reject_reasons"):
        print("Reject reasons:")
        for r in result["reject_reasons"]:
            print(f"  - {r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
