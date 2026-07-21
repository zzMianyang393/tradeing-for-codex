"""Append-only integrity checks for prospective observation registries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


IDENTITY_FIELDS = (
    "observation_id",
    "candidate_id",
    "rule_version",
    "signal_ts",
    "symbol",
    "direction",
    "regime",
    "maturity_ts",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_observation(observation: dict[str, Any]) -> dict[str, Any]:
    return {field: observation.get(field) for field in IDENTITY_FIELDS}


def build_baseline(registry: dict[str, Any]) -> dict[str, Any]:
    observations = sorted(
        (canonical_observation(item) for item in registry.get("observations", [])),
        key=lambda item: str(item["observation_id"]),
    )
    return {
        "baseline_type": "prospective_observation_append_only_baseline",
        "baseline_version": "v1.0.0",
        "observation_only": True,
        "source_common_data_cutoff": registry.get("common_data_cutoff"),
        "baseline_observation_count": len(observations),
        "baseline_max_signal_ts": max((int(item["signal_ts"]) for item in observations), default=None),
        "observations": observations,
        "methodology_notes": [
            "Baseline stores prospective observation identity fields only.",
            "Future registries may append later observations but may not remove or alter this baseline.",
            "No market results or execution fields are stored.",
        ],
    }


def audit_append_only(baseline: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    baseline_by_id = {item["observation_id"]: item for item in baseline.get("observations", [])}
    registry_by_id = {
        item["observation_id"]: canonical_observation(item) for item in registry.get("observations", [])
    }
    baseline_max_signal_ts = baseline.get("baseline_max_signal_ts")

    missing_ids = sorted(set(baseline_by_id) - set(registry_by_id))
    altered_ids = sorted(
        observation_id
        for observation_id in set(baseline_by_id) & set(registry_by_id)
        if baseline_by_id[observation_id] != registry_by_id[observation_id]
    )
    appended_ids = sorted(set(registry_by_id) - set(baseline_by_id))
    backfilled_ids = sorted(
        observation_id
        for observation_id in appended_ids
        if baseline_max_signal_ts is not None
        and int(registry_by_id[observation_id]["signal_ts"]) <= int(baseline_max_signal_ts)
    )

    if missing_ids:
        issues.append(f"baseline observations missing from registry: {len(missing_ids)}")
    if altered_ids:
        issues.append(f"baseline observations altered in registry: {len(altered_ids)}")
    if backfilled_ids:
        issues.append(f"new observations are backfilled at or before baseline maximum timestamp: {len(backfilled_ids)}")

    return {
        "audit_type": "prospective_observation_append_only",
        "baseline_version": baseline.get("baseline_version"),
        "observation_only": True,
        "append_only_status": "valid" if not issues else "invalid",
        "n_issues": len(issues),
        "issues": issues,
        "baseline_observation_count": len(baseline_by_id),
        "registry_observation_count": len(registry_by_id),
        "unchanged_baseline_count": len(baseline_by_id) - len(missing_ids) - len(altered_ids),
        "appended_observation_count": len(appended_ids),
        "missing_baseline_observation_ids": missing_ids,
        "altered_baseline_observation_ids": altered_ids,
        "backfilled_observation_ids": backfilled_ids,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check append-only prospective observation integrity.")
    parser.add_argument("--registry", type=Path, default=Path("reports/prospective_observation_registry.json"))
    parser.add_argument("--baseline", type=Path, default=Path("reports/prospective_observation_append_only_baseline.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_observation_append_audit.json"))
    parser.add_argument("--initialize-baseline", action="store_true")
    args = parser.parse_args(argv)

    registry = load_json(args.registry)
    if args.initialize_baseline:
        baseline = build_baseline(registry)
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    elif args.baseline.exists():
        baseline = load_json(args.baseline)
    else:
        print("ERROR: baseline does not exist; run once with --initialize-baseline")
        return 1

    report = audit_append_only(baseline, registry)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Append-only audit: {report['append_only_status']} ({report['n_issues']} issues)")
    return 0 if report["append_only_status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
