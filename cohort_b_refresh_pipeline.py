"""Cohort B append-only refresh pipeline.

Independent pipeline for Cohort B observations.
NEVER reads, modifies, or overwrites Cohort A files.

Pipeline:
  1. Build staging Cohort B registry from Cohort B ledger
  2. Validate append-only against Cohort B checkpoint
  3. Transactional publish with backup+rollback

Default: dry-run.  --commit only when new_count > 0 and all valid.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


REPORTS = Path("reports")

# Cohort B paths (NEVER touch Cohort A)
COHORT_B_LEDGER = REPORTS / "prospective_cohort_b_shadow_ledger.json"
COHORT_B_REGISTRY = REPORTS / "prospective_cohort_b_observation_registry.json"
COHORT_B_MATURITY = REPORTS / "prospective_cohort_b_maturity_audit.json"
COHORT_B_CHECKPOINT = REPORTS / "prospective_cohort_b_observation_checkpoint.json"

STAGING = REPORTS / "staging_cohort_b"
STAGING_LEDGER = STAGING / "prospective_cohort_b_shadow_ledger.json"
STAGING_REGISTRY = STAGING / "prospective_cohort_b_observation_registry.json"
STAGING_MATURITY = STAGING / "prospective_cohort_b_maturity_audit.json"

PUBLISH_FILES = [
    (STAGING_LEDGER, COHORT_B_LEDGER),
    (STAGING_REGISTRY, COHORT_B_REGISTRY),
    (STAGING_MATURITY, COHORT_B_MATURITY),
]

OBSERVATION_HORIZON_DAYS = 90
DAY_MS = 24 * 3600 * 1000


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


def compute_identity_hash(candidate_id, rule_version, signal_ts, symbol, direction, regime) -> str:
    import hashlib
    payload = f"{candidate_id}|{rule_version}|{signal_ts}|{symbol}|{direction}|{regime}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_registry_from_ledger(ledger: dict) -> dict:
    """Build Cohort B observation registry from ledger."""
    signals = ledger.get("signals", [])
    observations = []
    for sig in signals:
        cid = sig.get("candidate_id", "")
        rv = sig.get("rule_version", "")
        sts = sig.get("signal_ts", 0)
        sym = sig.get("symbol", "")
        d = sig.get("direction", "")
        r = sig.get("regime", "")
        oid = compute_identity_hash(cid, rv, sts, sym, d, r)
        mat_ts = sts + OBSERVATION_HORIZON_DAYS * DAY_MS
        observations.append({
            "observation_id": oid,
            "candidate_id": cid,
            "rule_version": rv,
            "signal_ts": sts,
            "signal_timestamp_utc": sig.get("signal_timestamp_utc", ""),
            "symbol": sym,
            "direction": d,
            "regime": r,
            "observation_start_ts": sts,
            "maturity_ts": mat_ts,
            "maturity_timestamp_utc": datetime.fromtimestamp(
                mat_ts / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "observation_horizon_days": OBSERVATION_HORIZON_DAYS,
            "observation_only": True,
        })

    max_ts = max((o["signal_ts"] for o in observations), default=0)
    return {
        "registry_type": "prospective_cohort_b_observation_registry",
        "generation_date": "2026-07-14",
        "observation_only": True,
        "cohort_id": ledger.get("cohort_id", "prospective_cohort_b_2026-07-14"),
        "ledger_signal_count": ledger.get("signal_count", 0),
        "common_data_cutoff": ledger.get("common_data_cutoff", ""),
        "registry_signal_count": len(observations),
        "max_signal_ts": max_ts,
        "observations": observations,
    }


def build_checkpoint_from_registry(registry: dict, genesis: dict | None = None) -> dict:
    observations = registry.get("observations", [])
    identities = {}
    for obs in observations:
        identities[obs["observation_id"]] = {
            k: obs[k] for k in
            ["observation_id", "candidate_id", "signal_ts", "symbol", "direction", "regime", "maturity_ts"]
        }
    max_ts = max((o["signal_ts"] for o in observations), default=0)
    cutoff = registry.get("common_data_cutoff", "")
    # Genesis defaults to EMPTY for Cohort B (first signal is append, not genesis)
    if genesis is not None:
        genesis_count = genesis.get("genesis_count", 0)
        genesis_identities = genesis.get("genesis_identities", {})
        genesis_cutoff = genesis.get("genesis_cutoff", "")
    else:
        genesis_count = 0
        genesis_identities = {}
        genesis_cutoff = ""

    return {
        "checkpoint_type": "prospective_cohort_b_observation_checkpoint",
        "cohort_id": registry.get("cohort_id", "prospective_cohort_b_2026-07-14"),
        "genesis_count": genesis_count,
        "genesis_cutoff": genesis_cutoff,
        "genesis_identities": genesis_identities,
        "current_count": len(observations),
        "current_cutoff": cutoff,
        "max_signal_ts": max_ts,
        "identities": identities,
        "observation_only": True,
    }


def validate_append_only(checkpoint: dict, staging_registry: dict) -> dict:
    issues = []
    cp_ids = set(checkpoint.get("identities", {}).keys())
    st_obs = staging_registry.get("observations", [])
    st_ids = {o["observation_id"] for o in st_obs}

    # All checkpoint observations must exist unchanged
    for oid, cp_o in checkpoint.get("identities", {}).items():
        match = next((o for o in st_obs if o["observation_id"] == oid), None)
        if match is None:
            issues.append(f"Checkpoint observation {oid} missing")
        else:
            for f in ["candidate_id", "signal_ts", "symbol", "direction", "regime", "maturity_ts"]:
                if match.get(f) != cp_o.get(f):
                    issues.append(f"Observation {oid}: field '{f}' changed")

    # New observations must have signal_ts > max
    cp_max = checkpoint.get("max_signal_ts", 0)
    new_ids = st_ids - cp_ids
    for o in st_obs:
        if o["observation_id"] in new_ids and o["signal_ts"] <= cp_max:
            issues.append(f"New observation {o['observation_id']}: signal_ts <= checkpoint max")

    # No duplicates
    if len(st_ids) != len(st_obs):
        issues.append("Duplicate observation_ids")

    # Hash consistency
    for o in st_obs:
        expected = compute_identity_hash(
            o["candidate_id"], o.get("rule_version", ""),
            o["signal_ts"], o["symbol"], o["direction"], o["regime"]
        )
        if o["observation_id"] != expected:
            issues.append(f"Hash mismatch for {o['observation_id']}")

    # Cutoff regression
    st_cut = staging_registry.get("common_data_cutoff", "")
    cp_cut = checkpoint.get("current_cutoff", "")
    if st_cut and cp_cut and st_cut < cp_cut:
        issues.append(f"Cutoff regressed: {st_cut} < {cp_cut}")

    return {
        "valid": len(issues) == 0,
        "n_issues": len(issues),
        "issues": issues,
        "checkpoint_count": len(cp_ids),
        "staging_count": len(st_obs),
        "new_count": len(new_ids),
    }


def transactional_publish(pairs, checkpoint_data, _fail_at=None):
    """Publish with backup+rollback. Not atomic multi-file replace."""
    checkpoint_path = COHORT_B_CHECKPOINT
    backups, tmp_files, replaced, new_created = [], [], [], []

    try:
        # Back up existing files
        for _, dst in pairs:
            if dst.exists():
                bak = dst.with_suffix(dst.suffix + ".bak")
                bak.write_bytes(dst.read_bytes())
                backups.append((dst, bak))
        if checkpoint_path.exists():
            bak = checkpoint_path.with_suffix(".bak")
            bak.write_bytes(checkpoint_path.read_bytes())
            backups.append((checkpoint_path, bak))

        # Write staging to tmp
        for src, dst in pairs:
            if not src.exists():
                raise FileNotFoundError(f"Staging missing: {src}")
            fd, tp = tempfile.mkstemp(dir=str(dst.parent), suffix=".tmp")
            os.close(fd)
            tmp = Path(tp)
            tmp.write_bytes(src.read_bytes())
            tmp_files.append(tmp)
            if not dst.exists():
                new_created.append(dst)

        # Write checkpoint tmp
        fd, tp = tempfile.mkstemp(dir=str(checkpoint_path.parent), suffix=".tmp")
        os.close(fd)
        cp_tmp = Path(tp)
        cp_tmp.write_text(json.dumps(checkpoint_data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_files.append(cp_tmp)
        if not checkpoint_path.exists():
            new_created.append(checkpoint_path)

        # Replace
        all_repl = [(tmp_files[i], pairs[i][1]) for i in range(len(pairs))]
        all_repl.append((cp_tmp, checkpoint_path))
        for step, (tmp, dst) in enumerate(all_repl):
            if _fail_at is not None and step == _fail_at:
                raise OSError(f"Injected failure at step {step}")
            os.replace(str(tmp), str(dst))
            replaced.append((tmp, dst))
            if tmp in tmp_files:
                tmp_files.remove(tmp)

        return {"success": True, "published": [str(d) for _, d in replaced],
                "rollback_attempted": False, "rollback_succeeded": None}

    except Exception as e:
        ok = True
        for orig, bak in backups:
            try:
                if bak.exists():
                    os.replace(str(bak), str(orig))
            except OSError:
                ok = False
        for dst in new_created:
            try:
                if dst.exists():
                    dst.unlink()
            except OSError:
                ok = False
        for tmp in tmp_files:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        for _, bak in backups:
            try:
                bak.unlink(missing_ok=True)
            except OSError:
                pass
        return {"success": False, "error": str(e),
                "published": [str(d) for _, d in replaced],
                "rollback_attempted": True, "rollback_succeeded": ok}


def run_pipeline(staging_ledger_path=None, commit=False):
    checkpoint = load_json(COHORT_B_CHECKPOINT)
    if checkpoint is None:
        # Create empty genesis checkpoint (no observations at genesis)
        checkpoint = {
            "checkpoint_type": "prospective_cohort_b_observation_checkpoint",
            "cohort_id": "prospective_cohort_b_2026-07-14",
            "genesis_count": 0,
            "genesis_cutoff": "",
            "genesis_identities": {},
            "current_count": 0,
            "current_cutoff": "",
            "max_signal_ts": 0,
            "identities": {},
            "observation_only": True,
        }
        save_json(COHORT_B_CHECKPOINT, checkpoint)

    source_ledger = load_json(staging_ledger_path or COHORT_B_LEDGER)
    if not source_ledger:
        return {"status": "error", "reason": "Cannot load Cohort B ledger"}

    # Stage: build registry from ledger
    staging_reg = build_registry_from_ledger(source_ledger)
    save_json(STAGING_REGISTRY, staging_reg)
    save_json(STAGING_LEDGER, source_ledger)

    # Build maturity stub
    cutoff_str = source_ledger.get("common_data_cutoff", "")
    cutoff_ts = int(datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc).timestamp() * 1000) if cutoff_str else 0
    mat = {
        "audit_type": "prospective_cohort_b_maturity",
        "observation_only": True,
        "as_of_ts": cutoff_ts,
        "as_of_utc": cutoff_str,
        "n_observations": staging_reg["registry_signal_count"],
        "n_awaiting": staging_reg["registry_signal_count"],
        "n_mature": 0,
        "safety_gates": {
            "approved_for_paper": [], "eligible_for_paper": False,
            "safe_to_enable_trading": False, "ready_for_combo_backtest": False,
        },
    }
    save_json(STAGING_MATURITY, mat)

    # Validate
    append = validate_append_only(checkpoint, staging_reg)
    new_count = append["new_count"]

    if not append["valid"]:
        decision = "rejected"
    elif new_count == 0:
        decision = "no_changes"
    else:
        decision = "ready_to_commit"

    result = {
        "pipeline_type": "cohort_b_refresh",
        "run_date": "2026-07-14",
        "observation_only": True,
        "mode": "commit" if commit else "dry_run",
        "refresh_decision": decision,
        "append_validation": append,
        "new_observations": new_count,
        "published": False,
    }

    if commit and decision == "ready_to_commit":
        genesis = {
            "genesis_count": checkpoint.get("genesis_count", 0),
            "genesis_identities": checkpoint.get("genesis_identities", {}),
            "genesis_cutoff": checkpoint.get("genesis_cutoff", ""),
        }
        new_cp = build_checkpoint_from_registry(staging_reg, genesis)
        pub = transactional_publish(PUBLISH_FILES, new_cp)
        result["published"] = pub["success"]
        result["publish_detail"] = pub
        if not pub["success"]:
            result["reject_reasons"] = [f"Publish failed: {pub.get('error')}"]
    elif decision == "rejected":
        result["reject_reasons"] = append["issues"]
    elif decision == "no_changes":
        result["reject_reasons"] = ["No new observations"]

    save_json(REPORTS / "cohort_b_refresh_pipeline.json", result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--staging-ledger", type=Path, default=None)
    p.add_argument("--commit", action="store_true")
    p.add_argument("--init-checkpoint", action="store_true")
    args = p.parse_args(argv)

    if args.init_checkpoint:
        # Genesis is always EMPTY for Cohort B
        # Real observations are appended via pipeline, not baked into genesis
        ledger = load_json(COHORT_B_LEDGER)
        cutoff = ledger.get("common_data_cutoff", "") if ledger else ""
        cp = {
            "checkpoint_type": "prospective_cohort_b_observation_checkpoint",
            "cohort_id": "prospective_cohort_b_2026-07-14",
            "genesis_count": 0,
            "genesis_cutoff": "",
            "genesis_identities": {},
            "current_count": 0,
            "current_cutoff": "",
            "max_signal_ts": 0,
            "identities": {},
            "observation_only": True,
        }
        save_json(COHORT_B_CHECKPOINT, cp)
        print(f"Checkpoint initialized: genesis=0, current=0")
        return 0

    result = run_pipeline(args.staging_ledger, args.commit)
    print(f"Decision: {result['refresh_decision']}")
    print(f"New: {result['new_observations']}, Published: {result.get('published', False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
