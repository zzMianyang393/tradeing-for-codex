from __future__ import annotations

import ast
import json
from pathlib import Path

from prospective_observation_append_audit import audit_append_only, build_baseline


def _registry(observations: list[dict]) -> dict:
    return {"common_data_cutoff": "2026-07-13 08:15:00", "observations": observations}


def _observation(observation_id: str, signal_ts: int = 100) -> dict:
    return {
        "observation_id": observation_id,
        "candidate_id": "candidate",
        "rule_version": "frozen",
        "signal_ts": signal_ts,
        "symbol": "BTC-USDT-SWAP",
        "direction": "long",
        "regime": "趋势上行",
        "maturity_ts": signal_ts + 90,
    }


def test_identical_registry_passes_append_only_audit() -> None:
    registry = _registry([_observation("one"), _observation("two", 200)])
    report = audit_append_only(build_baseline(registry), registry)
    assert report["append_only_status"] == "valid"
    assert report["unchanged_baseline_count"] == 2
    assert report["appended_observation_count"] == 0


def test_later_signal_is_allowed_append() -> None:
    baseline_registry = _registry([_observation("one", 100)])
    current_registry = _registry([_observation("one", 100), _observation("two", 101)])
    report = audit_append_only(build_baseline(baseline_registry), current_registry)
    assert report["append_only_status"] == "valid"
    assert report["appended_observation_count"] == 1


def test_missing_or_backfilled_observation_fails() -> None:
    baseline_registry = _registry([_observation("one", 100)])
    missing = audit_append_only(build_baseline(baseline_registry), _registry([]))
    backfilled = audit_append_only(
        build_baseline(baseline_registry), _registry([_observation("one", 100), _observation("two", 100)])
    )
    assert missing["append_only_status"] == "invalid"
    assert backfilled["append_only_status"] == "invalid"


def test_current_baseline_and_registry_are_valid() -> None:
    baseline_path = Path("reports/prospective_observation_append_only_baseline.json")
    report_path = Path("reports/prospective_observation_append_audit.json")
    if not baseline_path.exists() or not report_path.exists():
        return
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert baseline["baseline_observation_count"] == 28
    assert report["append_only_status"] == "valid"


def test_module_has_no_runner_import() -> None:
    tree = ast.parse(Path("prospective_observation_append_audit.py").read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "runner" not in imports
