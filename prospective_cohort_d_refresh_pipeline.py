"""Append-only, future-only metadata refresh pipeline for Cohort D."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prospective_cohort_d_cross_sectional_weakness import ACTIVATION_TS, COHORT_ID, build


REPORTS = Path("reports")
FORMAL_LEDGER = REPORTS / "prospective_cohort_d_cross_sectional_weakness_ledger.json"
FORMAL_REGISTRY = REPORTS / "prospective_cohort_d_observation_registry.json"
FORMAL_MATURITY = REPORTS / "prospective_cohort_d_maturity_audit.json"
CHECKPOINT = REPORTS / "prospective_cohort_d_observation_checkpoint.json"
PIPELINE_REPORT = REPORTS / "cohort_d_refresh_pipeline.json"
STAGING = REPORTS / "staging_cohort_d"
DAY_MS = 86_400_000
HORIZON_DAYS = 90


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def identity(signal: dict[str, Any]) -> str:
    values = (signal.get("hypothesis_id", ""), signal.get("rule_version", ""), str(signal.get("signal_ts", "")),
              signal.get("symbol", ""), signal.get("direction", ""), signal.get("regime", ""))
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:16]


def build_registry(ledger: dict[str, Any]) -> dict[str, Any]:
    observations = []
    for signal in ledger.get("signals", []):
        signal_ts = int(signal["signal_ts"])
        maturity_ts = signal_ts + HORIZON_DAYS * DAY_MS
        observations.append({
            "observation_id": identity(signal), "hypothesis_id": signal["hypothesis_id"],
            "rule_version": signal["rule_version"], "signal_ts": signal_ts,
            "signal_timestamp_utc": signal["signal_timestamp_utc"], "symbol": signal["symbol"],
            "direction": signal["direction"], "regime": signal["regime"], "maturity_ts": maturity_ts,
            "maturity_timestamp_utc": datetime.fromtimestamp(maturity_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "observation_horizon_days": HORIZON_DAYS, "observation_only": True,
        })
    observations.sort(key=lambda row: (row["signal_ts"], row["symbol"]))
    return {
        "registry_type": "prospective_cohort_d_observation_registry", "cohort_id": ledger.get("cohort_id", COHORT_ID),
        "hypothesis_id": ledger.get("hypothesis_id", ""), "common_data_cutoff": ledger.get("common_data_cutoff", ""),
        "registry_signal_count": len(observations), "max_signal_ts": max((row["signal_ts"] for row in observations), default=0),
        "observations": observations, "observation_only": True, "safety_gates": ledger.get("safety_gates", {}),
    }


def empty_checkpoint() -> dict[str, Any]:
    return {"checkpoint_type": "prospective_cohort_d_observation_checkpoint", "cohort_id": COHORT_ID,
            "current_count": 0, "current_cutoff": "", "max_signal_ts": 0, "identities": {}, "observation_only": True}


def validate_append_only(checkpoint: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    observations = registry.get("observations", [])
    by_id = {row.get("observation_id"): row for row in observations}
    prior = checkpoint.get("identities", {})
    if len(by_id) != len(observations):
        issues.append("Duplicate observation identities.")
    immutable = ("hypothesis_id", "rule_version", "signal_ts", "symbol", "direction", "regime", "maturity_ts")
    for observation_id, stored in prior.items():
        row = by_id.get(observation_id)
        if row is None:
            issues.append(f"Existing observation {observation_id} missing.")
        elif any(row.get(key) != stored.get(key) for key in immutable):
            issues.append(f"Existing observation {observation_id} changed.")
    new_ids = set(by_id) - set(prior)
    for observation_id in new_ids:
        row = by_id[observation_id]
        if row["signal_ts"] < ACTIVATION_TS:
            issues.append(f"New observation {observation_id} predates activation.")
        if row["signal_ts"] <= checkpoint.get("max_signal_ts", 0):
            issues.append(f"New observation {observation_id} is not strictly append-only.")
        if observation_id != identity(row):
            issues.append(f"New observation {observation_id} has invalid identity.")
    cutoff = registry.get("common_data_cutoff", "")
    if checkpoint.get("current_cutoff") and cutoff < checkpoint["current_cutoff"]:
        issues.append("Data cutoff regressed.")
    return {"valid": not issues, "issues": issues, "checkpoint_count": len(prior), "staging_count": len(observations), "new_count": len(new_ids)}


def maturity(registry: dict[str, Any]) -> dict[str, Any]:
    cutoff = registry.get("common_data_cutoff", "")
    cutoff_ts = int(datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000) if cutoff else 0
    rows = []
    for observation in registry.get("observations", []):
        status = "awaiting_maturity" if cutoff_ts < observation["maturity_ts"] else "mature_awaiting_sealed_evaluation"
        rows.append({key: observation[key] for key in ("observation_id", "hypothesis_id", "symbol", "signal_ts", "maturity_ts", "maturity_timestamp_utc")})
        rows[-1]["status"] = status
    counts = Counter(row["status"] for row in rows)
    return {"audit_type": "prospective_cohort_d_maturity", "cohort_id": registry.get("cohort_id", COHORT_ID),
            "as_of_utc": cutoff, "as_of_ts": cutoff_ts, "source_cutoff": cutoff, "n_observations": len(rows),
            "status_counts": dict(counts), "n_awaiting": counts.get("awaiting_maturity", 0),
            "n_mature_awaiting_sealed_evaluation": counts.get("mature_awaiting_sealed_evaluation", 0),
            "observations": rows, "outcomes_evaluated": False, "observation_only": True,
            "safety_gates": registry.get("safety_gates", {})}


def checkpoint_from_registry(registry: dict[str, Any]) -> dict[str, Any]:
    keys = ("observation_id", "hypothesis_id", "rule_version", "signal_ts", "symbol", "direction", "regime", "maturity_ts")
    observations = registry.get("observations", [])
    return {"checkpoint_type": "prospective_cohort_d_observation_checkpoint", "cohort_id": registry.get("cohort_id", COHORT_ID),
            "current_count": len(observations), "current_cutoff": registry.get("common_data_cutoff", ""),
            "max_signal_ts": max((row["signal_ts"] for row in observations), default=0),
            "identities": {row["observation_id"]: {key: row[key] for key in keys} for row in observations}, "observation_only": True}


def transactional_publish(pairs: list[tuple[Path, Path]], checkpoint: dict[str, Any], checkpoint_path: Path, fail_at: int | None = None) -> dict[str, Any]:
    backups: list[tuple[Path, Path]] = []
    temps: list[Path] = []
    created: list[Path] = []
    try:
        for _, destination in [*pairs, (Path(), checkpoint_path)]:
            if destination.exists():
                backup = destination.with_suffix(destination.suffix + ".bak")
                backup.write_bytes(destination.read_bytes()); backups.append((destination, backup))
            else:
                created.append(destination)
        replacements = []
        for source, destination in pairs:
            fd, raw = tempfile.mkstemp(dir=str(destination.parent), suffix=".tmp"); os.close(fd)
            temp = Path(raw); temp.write_bytes(source.read_bytes()); temps.append(temp); replacements.append((temp, destination))
        fd, raw = tempfile.mkstemp(dir=str(checkpoint_path.parent), suffix=".tmp"); os.close(fd)
        temp = Path(raw); temp.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8"); temps.append(temp); replacements.append((temp, checkpoint_path))
        for index, (temp, destination) in enumerate(replacements):
            if fail_at == index:
                raise OSError(f"Injected failure {index}")
            os.replace(str(temp), str(destination)); temps.remove(temp)
        return {"success": True, "rollback_attempted": False}
    except OSError as exc:
        ok = True
        for destination, backup in backups:
            try: os.replace(str(backup), str(destination))
            except OSError: ok = False
        for destination in created:
            try: destination.unlink(missing_ok=True)
            except OSError: ok = False
        return {"success": False, "error": str(exc), "rollback_attempted": True, "rollback_succeeded": ok}
    finally:
        for temp in temps: temp.unlink(missing_ok=True)
        for _, backup in backups: backup.unlink(missing_ok=True)


def run_pipeline(data_dir: Path, commit: bool = False, reports_dir: Path = REPORTS) -> dict[str, Any]:
    formal_ledger = reports_dir / FORMAL_LEDGER.name; formal_registry = reports_dir / FORMAL_REGISTRY.name
    formal_maturity = reports_dir / FORMAL_MATURITY.name; checkpoint_path = reports_dir / CHECKPOINT.name
    staging = reports_dir / STAGING.name
    ledger = build(data_dir); registry = build_registry(ledger); audit = maturity(registry)
    checkpoint = load_json(checkpoint_path) or empty_checkpoint(); append = validate_append_only(checkpoint, registry)
    new_count = append["new_count"]
    decision = "rejected" if not append["valid"] else "no_changes" if new_count == 0 else "ready_to_commit"
    staging_ledger, staging_registry, staging_maturity = staging / FORMAL_LEDGER.name, staging / FORMAL_REGISTRY.name, staging / FORMAL_MATURITY.name
    save_json(staging_ledger, ledger); save_json(staging_registry, registry); save_json(staging_maturity, audit)
    result = {"pipeline_type": "prospective_cohort_d_refresh", "cohort_id": COHORT_ID, "observation_only": True,
              "mode": "commit" if commit else "dry_run", "coverage_status": ledger["coverage_status"],
              "common_data_cutoff": ledger.get("common_data_cutoff", ""), "refresh_decision": decision,
              "new_observations": new_count, "append_validation": append, "published": False,
              "outcomes_evaluated": False, "positions_opened": False, "safety_gates": ledger["safety_gates"]}
    if commit and decision == "ready_to_commit":
        published = transactional_publish([(staging_ledger, formal_ledger), (staging_registry, formal_registry), (staging_maturity, formal_maturity)], checkpoint_from_registry(registry), checkpoint_path)
        result["published"] = published["success"]; result["publish_detail"] = published
    save_json(reports_dir / PIPELINE_REPORT.name, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--data", type=Path, default=Path("data")); parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv); result = run_pipeline(args.data, args.commit)
    print(f"decision={result['refresh_decision']}; new={result['new_observations']}; published={str(result['published']).lower()}")
    return 0 if result["refresh_decision"] != "rejected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
