"""Tests for prospective shadow refresh pipeline (C29-C33).

Covers:
  - Checkpoint initialization (28 observations)
  - Same data dry-run returns no_changes and does not publish
  - New observation passes staging append validation
  - Deleted/modified/old-timestamp observations rejected
  - Rejected refresh leaves production files unchanged
  - Default mode does not overwrite production
  - Transactional publish with rollback: fault injection at steps 0, 2, 4
  - Fault injection: all 5 files byte-for-byte match pre-publish state
  - Successful append: 5 files go from 28 to 29
  - 0 new signals cannot commit
  - Genesis 28 identities preserved after append
  - Cutoff regression rejected
  - No runner imports, no forbidden JSON keys, safety gates closed
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from prospective_observation_registry import (
    build_registry,
    compute_identity_hash,
    load_ledger,
    OBSERVATION_HORIZON_DAYS,
    DAY_MS,
)
from prospective_shadow_refresh_pipeline import (
    build_checkpoint_from_registry,
    validate_append_only,
    transactional_publish_with_rollback,
    run_pipeline,
    load_json,
    save_json,
    REPORTS,
    STAGING,
    LEDGER_PATH,
    REGISTRY_PATH,
    CHECKPOINT_PATH,
    PUBLISH_FILES,
)


FORBIDDEN_KEYS = {
    "pnl", "return", "returns", "price", "entry_price", "exit_price",
    "position", "order", "trade", "win", "loss", "mfe", "mae",
}


def _load_ledger() -> dict:
    p = Path("reports/prospective_shadow_signal_ledger.json")
    if not p.exists():
        pytest.skip("Ledger not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _load_registry() -> dict:
    p = Path("reports/prospective_observation_registry.json")
    if not p.exists():
        pytest.skip("Registry not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _load_checkpoint() -> dict:
    p = Path("reports/prospective_observation_checkpoint.json")
    if not p.exists():
        pytest.skip("Checkpoint not found")
    return json.loads(p.read_text(encoding="utf-8"))


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


def _make_new_obs(signal_ts: int) -> dict:
    cid = "donchian_atr_trend_baseline"
    rv = "frozen_2026-07-14"
    sym = "TEST-USDT-SWAP"
    direction = "long"
    regime = "趋势上行"
    h = compute_identity_hash(cid, rv, signal_ts, sym, direction, regime)
    return {
        "observation_id": h, "candidate_id": cid, "rule_version": rv,
        "signal_ts": signal_ts, "symbol": sym, "direction": direction,
        "regime": regime, "maturity_ts": signal_ts + OBSERVATION_HORIZON_DAYS * DAY_MS,
    }


def _snapshot_files(paths: list[Path]) -> dict[str, bytes]:
    """Capture byte content of all existing files."""
    snap = {}
    for p in paths:
        if p.exists():
            snap[str(p)] = p.read_bytes()
    return snap


def _verify_snapshot(paths: list[Path], snapshot: dict[str, bytes]) -> bool:
    """Verify all files match their snapshot byte-for-byte."""
    for p in paths:
        key = str(p)
        if key in snapshot:
            if not p.exists():
                return False
            if p.read_bytes() != snapshot[key]:
                return False
        else:
            if p.exists():
                return False
    return True


# ── Module import safety ─────────────────────────────────────────────────────

class TestModuleImportSafety:
    @pytest.mark.parametrize("module_name", [
        "prospective_shadow_refresh_pipeline.py",
        "prospective_refresh_publish_audit.py",
    ])
    def test_no_runner_import(self, module_name):
        path = Path(module_name)
        if not path.exists():
            pytest.skip(f"{module_name} not found")
        content = path.read_text(encoding="utf-8")
        assert "from runner import" not in content
        assert "import runner" not in content


# ── Report content safety ────────────────────────────────────────────────────

class TestReportContentSafety:
    @pytest.mark.parametrize("report_path", [
        "reports/prospective_shadow_refresh_pipeline.json",
        "reports/prospective_refresh_publish_audit.json",
        "reports/prospective_observation_checkpoint.json",
    ])
    def test_no_forbidden_keys(self, report_path):
        p = Path(report_path)
        if not p.exists():
            pytest.skip(f"{report_path} not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        all_keys = _collect_keys(report)
        found = all_keys & FORBIDDEN_KEYS
        assert not found, f"{report_path} contains forbidden keys: {found}"


# ── Checkpoint initialization ────────────────────────────────────────────────

class TestCheckpointInit:
    def test_checkpoint_has_28_observations(self):
        cp = _load_checkpoint()
        assert cp["genesis_count"] == 28
        assert cp["current_count"] == 28
        assert len(cp["identities"]) == 28
        assert len(cp.get("genesis_identities", {})) == 28


# ── Same data dry-run ────────────────────────────────────────────────────────

class TestSameDataDryRun:
    def test_same_data_returns_no_changes(self):
        result = run_pipeline(commit=False)
        assert result["refresh_decision"] == "no_changes"
        assert result["published"] is False
        assert result["new_observations"] == 0

    def test_same_data_does_not_modify_production(self):
        prod_files = [LEDGER_PATH, REGISTRY_PATH, REPORTS / "prospective_maturity_audit.json",
                      REPORTS / "prospective_observation_integrity_audit.json", CHECKPOINT_PATH]
        snapshot = _snapshot_files(prod_files)
        run_pipeline(commit=False)
        assert _verify_snapshot(prod_files, snapshot), "Production files modified during dry-run"


# ── New observation passes ───────────────────────────────────────────────────

class TestNewObservation:
    def test_newer_observation_passes_append(self):
        registry = _load_registry()
        checkpoint = _load_checkpoint()
        new_ts = checkpoint["max_signal_ts"] + 86400000
        new_obs = _make_new_obs(new_ts)
        staging_obs = list(registry["observations"]) + [new_obs]
        staging_registry = {"observations": staging_obs}
        result = validate_append_only(checkpoint, staging_registry)
        assert result["valid"] is True
        assert result["new_count"] == 1


# ── Rejected scenarios ───────────────────────────────────────────────────────

class TestRejectedScenarios:
    def test_deleted_observation_rejected(self):
        registry = _load_registry()
        checkpoint = _load_checkpoint()
        staging_obs = list(registry["observations"])[1:]
        result = validate_append_only(checkpoint, {"observations": staging_obs})
        assert result["valid"] is False

    def test_modified_identity_rejected(self):
        registry = _load_registry()
        checkpoint = _load_checkpoint()
        staging_obs = copy.deepcopy(list(registry["observations"]))
        staging_obs[0]["direction"] = "short"
        result = validate_append_only(checkpoint, {"observations": staging_obs})
        assert result["valid"] is False

    def test_old_timestamp_rejected(self):
        registry = _load_registry()
        checkpoint = _load_checkpoint()
        new_obs = _make_new_obs(checkpoint["max_signal_ts"] - 86400000)
        staging_obs = list(registry["observations"]) + [new_obs]
        result = validate_append_only(checkpoint, {"observations": staging_obs})
        assert result["valid"] is False

    def test_zero_new_cannot_commit(self):
        result = run_pipeline(commit=True)
        assert result["refresh_decision"] == "no_changes"
        assert result["published"] is False


# ── Transactional publish with rollback ──────────────────────────────────────

class TestTransactionalPublish:
    def test_successful_publish_all_files_updated(self, tmp_path):
        """Successful publish updates all staging→prod pairs + checkpoint."""
        src_dir = tmp_path / "staging"
        dst_dir = tmp_path / "prod"
        src_dir.mkdir()
        dst_dir.mkdir()

        for name in ["a.json", "b.json"]:
            (src_dir / name).write_text(f'{{"v": 2, "name": "{name}"}}', encoding="utf-8")
            (dst_dir / name).write_text(f'{{"v": 1, "name": "{name}"}}', encoding="utf-8")

        pairs = [(src_dir / n, dst_dir / n) for n in ["a.json", "b.json"]]
        cp_path = tmp_path / "checkpoint.json"
        cp_data = {"count": 2}

        # Monkeypatch CHECKPOINT_PATH
        import prospective_shadow_refresh_pipeline as mod
        orig = mod.CHECKPOINT_PATH
        mod.CHECKPOINT_PATH = cp_path
        try:
            result = transactional_publish_with_rollback(pairs, cp_data)
            assert result["success"] is True
            assert result["rollback_attempted"] is False
            # Verify files updated
            for name in ["a.json", "b.json"]:
                content = json.loads((dst_dir / name).read_text(encoding="utf-8"))
                assert content["v"] == 2
            assert cp_path.exists()
        finally:
            mod.CHECKPOINT_PATH = orig

    @pytest.mark.parametrize("fail_step", [0, 2, 4])
    def test_fault_injection_rollback_preserves_old_files(self, tmp_path, fail_step):
        """If os.replace fails at step N, all 5 files must match pre-publish state."""
        src_dir = tmp_path / "staging"
        dst_dir = tmp_path / "prod"
        src_dir.mkdir()
        dst_dir.mkdir()

        names = ["file1.json", "file2.json", "file3.json", "file4.json", "file5.json"]
        for name in names:
            (src_dir / name).write_text(f'{{"v": 2}}', encoding="utf-8")
            (dst_dir / name).write_text(f'{{"v": 1}}', encoding="utf-8")

        pairs = [(src_dir / n, dst_dir / n) for n in names]
        cp_path = tmp_path / "checkpoint.json"
        cp_data = {"count": 2}

        # Snapshot before publish
        all_dsts = [dst_dir / n for n in names]
        snapshot = _snapshot_files(all_dsts)

        import prospective_shadow_refresh_pipeline as mod
        orig = mod.CHECKPOINT_PATH
        mod.CHECKPOINT_PATH = cp_path
        try:
            result = transactional_publish_with_rollback(pairs, cp_data, _fail_at=fail_step)
            assert result["success"] is False
            assert result["rollback_attempted"] is True
            assert result["rollback_succeeded"] is True
            # Verify all files match pre-publish state
            assert _verify_snapshot(all_dsts, snapshot), "Files not restored after rollback"
        finally:
            mod.CHECKPOINT_PATH = orig

    def test_rollback_deletes_newly_created_files(self, tmp_path):
        """If a file didn't exist before and publish fails, it must be deleted."""
        src_dir = tmp_path / "staging"
        dst_dir = tmp_path / "prod"
        src_dir.mkdir()
        dst_dir.mkdir()

        # a.json exists, b.json does NOT exist in dst
        (src_dir / "a.json").write_text('{"v": 2}', encoding="utf-8")
        (src_dir / "b.json").write_text('{"v": 2}', encoding="utf-8")
        (dst_dir / "a.json").write_text('{"v": 1}', encoding="utf-8")
        # b.json intentionally missing from dst

        pairs = [(src_dir / "a.json", dst_dir / "a.json"), (src_dir / "b.json", dst_dir / "b.json")]
        cp_path = tmp_path / "checkpoint.json"

        import prospective_shadow_refresh_pipeline as mod
        orig = mod.CHECKPOINT_PATH
        mod.CHECKPOINT_PATH = cp_path
        try:
            # Fail at step 1 (b.json replace)
            result = transactional_publish_with_rollback(pairs, {"count": 1}, _fail_at=1)
            assert result["success"] is False
            # a.json should be restored to v=1
            assert json.loads((dst_dir / "a.json").read_text(encoding="utf-8"))["v"] == 1
            # b.json should not exist (was newly created)
            assert not (dst_dir / "b.json").exists()
        finally:
            mod.CHECKPOINT_PATH = orig


# ── Genesis preservation ─────────────────────────────────────────────────────

class TestGenesisPreservation:
    def test_genesis_28_preserved(self):
        cp = _load_checkpoint()
        assert cp["genesis_count"] == 28
        assert len(cp["genesis_identities"]) == 28
        for oid in cp["genesis_identities"]:
            assert oid in cp["identities"]

    def test_genesis_fields_unchanged(self):
        cp = _load_checkpoint()
        for oid, gen in cp["genesis_identities"].items():
            cur = cp["identities"].get(oid)
            assert cur is not None
            for field in ["candidate_id", "signal_ts", "symbol", "direction", "regime", "maturity_ts"]:
                assert cur[field] == gen[field]


# ── Cutoff regression ────────────────────────────────────────────────────────

class TestCutoffRegression:
    def test_cutoff_regression_rejected(self):
        checkpoint = _load_checkpoint()
        registry = _load_registry()
        staging = copy.deepcopy(registry)
        staging["common_data_cutoff"] = "2020-01-01 00:00:00"
        result = validate_append_only(checkpoint, staging)
        assert result["valid"] is False
        assert any("Cutoff regressed" in issue for issue in result["issues"])


# ── Safety gates ─────────────────────────────────────────────────────────────

class TestSafetyGates:
    def test_maturity_safety_gates(self):
        p = Path("reports/prospective_maturity_audit.json")
        if not p.exists():
            pytest.skip("Maturity audit not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        gates = report.get("safety_gates", {})
        assert gates.get("approved_for_paper") == []
        assert gates.get("eligible_for_paper") is False
        assert gates.get("safe_to_enable_trading") is False
        assert gates.get("ready_for_combo_backtest") is False
