"""Tests for C39-C43: Cohort B pipeline, data quality, dashboard, prototype consistency."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cohort_b_refresh_pipeline import (
    build_registry_from_ledger,
    build_checkpoint_from_registry,
    validate_append_only,
    transactional_publish,
    compute_identity_hash,
    COHORT_B_CHECKPOINT,
)


def _load_json(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
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


FORBIDDEN = {"pnl", "return", "returns", "price", "entry_price", "exit_price",
             "position", "order", "trade", "win", "loss", "mfe", "mae", "veto"}


# ── C39: Cohort B pipeline ──────────────────────────────────────────────────

class TestCohortBPipeline:
    def test_no_runner_import(self):
        content = Path("cohort_b_refresh_pipeline.py").read_text(encoding="utf-8")
        assert "from runner import" not in content
        assert "import runner" not in content

    def test_same_data_returns_no_changes(self):
        from cohort_b_refresh_pipeline import run_pipeline
        result = run_pipeline(commit=False)
        assert result["refresh_decision"] == "no_changes"
        assert result["published"] is False

    def test_zero_new_cannot_commit(self):
        from cohort_b_refresh_pipeline import run_pipeline
        result = run_pipeline(commit=True)
        assert result["refresh_decision"] == "no_changes"
        assert result["published"] is False

    def test_append_only_rejects_deletion(self):
        ledger = {"signals": [{"candidate_id": "a", "rule_version": "v1", "signal_ts": 1000,
                               "symbol": "S", "direction": "long", "regime": "r"}]}
        reg = build_registry_from_ledger(ledger)
        cp = build_checkpoint_from_registry(reg)
        staging = {"observations": []}  # deleted
        result = validate_append_only(cp, staging)
        assert result["valid"] is False

    def test_append_only_rejects_modification(self):
        ledger = {"signals": [{"candidate_id": "a", "rule_version": "v1", "signal_ts": 1000,
                               "symbol": "S", "direction": "long", "regime": "r"}]}
        reg = build_registry_from_ledger(ledger)
        cp = build_checkpoint_from_registry(reg)
        staging_obs = copy.deepcopy(reg["observations"])
        staging_obs[0]["direction"] = "short"
        result = validate_append_only(cp, {"observations": staging_obs})
        assert result["valid"] is False

    def test_append_only_rejects_old_timestamp(self):
        ledger = {"signals": [{"candidate_id": "a", "rule_version": "v1", "signal_ts": 2000,
                               "symbol": "S", "direction": "long", "regime": "r"}]}
        reg = build_registry_from_ledger(ledger)
        cp = build_checkpoint_from_registry(reg)
        new_obs = copy.deepcopy(reg["observations"][0])
        new_obs["signal_ts"] = 500  # older
        new_obs["observation_id"] = compute_identity_hash("a", "v1", 500, "S", "long", "r")
        staging_obs = reg["observations"] + [new_obs]
        result = validate_append_only(cp, {"observations": staging_obs})
        assert result["valid"] is False

    def test_newer_observation_passes(self):
        ledger = {"signals": [{"candidate_id": "a", "rule_version": "v1", "signal_ts": 1000,
                               "symbol": "S", "direction": "long", "regime": "r"}]}
        reg = build_registry_from_ledger(ledger)
        cp = build_checkpoint_from_registry(reg)
        new_obs = {
            "observation_id": compute_identity_hash("a", "v1", 2000, "S", "long", "r"),
            "candidate_id": "a", "rule_version": "v1", "signal_ts": 2000,
            "symbol": "S", "direction": "long", "regime": "r", "maturity_ts": 2000 + 90*86400*1000,
        }
        staging_obs = reg["observations"] + [new_obs]
        result = validate_append_only(cp, {"observations": staging_obs})
        assert result["valid"] is True
        assert result["new_count"] == 1

    def test_fault_injection_rollback(self, tmp_path):
        """Simulate failure at step 1, verify rollback."""
        src_dir = tmp_path / "staging"
        dst_dir = tmp_path / "prod"
        src_dir.mkdir()
        dst_dir.mkdir()
        for n in ["a.json", "b.json", "c.json"]:
            (src_dir / n).write_text('{"v":2}', encoding="utf-8")
            (dst_dir / n).write_text('{"v":1}', encoding="utf-8")

        pairs = [(src_dir / n, dst_dir / n) for n in ["a.json", "b.json", "c.json"]]
        import cohort_b_refresh_pipeline as mod
        orig = mod.COHORT_B_CHECKPOINT
        mod.COHORT_B_CHECKPOINT = tmp_path / "cp.json"
        try:
            result = transactional_publish(pairs, {"test": True}, _fail_at=1)
            assert result["success"] is False
            assert result["rollback_attempted"] is True
            # a.json should be restored to v=1
            assert json.loads((dst_dir / "a.json").read_text())["v"] == 1
        finally:
            mod.COHORT_B_CHECKPOINT = orig

    def test_cohort_a_unchanged(self):
        """Cohort A checkpoint must not be modified by Cohort B operations."""
        ca = _load_json("reports/prospective_observation_checkpoint.json")
        if ca is None:
            pytest.skip("Cohort A checkpoint not found")
        assert ca.get("genesis_count") == 28

    def test_no_forbidden_keys(self):
        report = _load_json("reports/cohort_b_refresh_pipeline.json")
        if report is None:
            pytest.skip("Pipeline report not found")
        keys = _collect_keys(report)
        assert not keys & FORBIDDEN

    def test_empty_genesis_first_signal_preserves_genesis_zero(self):
        """Empty genesis + first signal commit must keep genesis_count=0."""
        cp = _load_json("reports/prospective_cohort_b_observation_checkpoint.json")
        if cp is None:
            pytest.skip("Cohort B checkpoint not found")
        assert cp["genesis_count"] == 0, f"genesis_count={cp['genesis_count']}, expected 0"
        assert len(cp["genesis_identities"]) == 0
        assert cp["current_count"] >= 1
        assert len(cp["identities"]) >= 1


# ── C42: Data quality ────────────────────────────────────────────────────────

class TestDataQuality:
    def test_report_exists(self):
        report = _load_json("reports/data_quality_audit.json")
        assert report is not None

    def test_28_eligible_symbols(self):
        report = _load_json("reports/data_quality_audit.json")
        if report is None:
            pytest.skip("Report not found")
        assert report["n_eligible_symbols"] == 28

    def test_common_cutoff_is_actual_minimum_latest_bar(self):
        """Live data coverage must follow the oldest latest audited bar, not a stale ledger snapshot."""
        report = _load_json("reports/data_quality_audit.json")
        if report is None:
            pytest.skip("Report not found")
        latest = [item["last_ts"] for item in report["per_symbol"] if "last_ts" in item]
        assert latest
        assert report["common_cutoff_ts"] == min(latest)

    def test_excluded_symbols_reported(self):
        """SEI and other non-frozen symbols must be in excluded_symbols."""
        report = _load_json("reports/data_quality_audit.json")
        if report is None:
            pytest.skip("Report not found")
        assert "SEI" in report.get("excluded_symbols", []), "SEI should be excluded"

    def test_no_returns_in_report(self):
        report = _load_json("reports/data_quality_audit.json")
        if report is None:
            pytest.skip("Report not found")
        keys = _collect_keys(report)
        assert not keys & {"return", "returns", "pnl", "price"}


# ── C43: Dashboard ──────────────────────────────────────────────────────────

class TestPrototypeConsistency:
    def test_universe_count_111(self):
        u = _load_json("reports/strategy_prototype_universe_111.json")
        if u is None:
            pytest.skip("Universe not found")
        assert u["prototype_count"] == 111
        assert len(u["prototypes"]) == 111

    def test_status_counts_sum_111(self):
        u = _load_json("reports/strategy_prototype_universe_111.json")
        if u is None:
            pytest.skip("Universe not found")
        total = sum(u["status_counts"].values())
        assert total == 111

    def test_preflight_decision_counts_sum_111(self):
        pf = _load_json("reports/strategy_prototype_batch_preflight.json")
        if pf is None:
            pytest.skip("Preflight not found")
        total = sum(pf["decision_counts"].values())
        assert total == 111

    def test_priority_count_13(self):
        pf = _load_json("reports/strategy_prototype_batch_preflight.json")
        if pf is None:
            pytest.skip("Preflight not found")
        assert len(pf["research_card_priority"]) == 13

    def test_no_blocked_in_priority(self):
        """No grid/martingale/funding/OI/HFT/external in priority."""
        pf = _load_json("reports/strategy_prototype_batch_preflight.json")
        if pf is None:
            pytest.skip("Preflight not found")
        blocked_tokens = ["oi", "funding", "网格", "马丁", "锁仓", "套利", "交割",
                          "价差", "宏观", "高频", "orderbook", "liquidation"]
        for item in pf["research_card_priority"]:
            name = item.get("name_cn", "").lower()
            for token in blocked_tokens:
                assert token not in name, f"Priority {item['prototype_id']} contains blocked token '{token}'"

    def test_safety_gates_closed(self):
        u = _load_json("reports/strategy_prototype_universe_111.json")
        if u is None:
            pytest.skip("Universe not found")
        gates = u.get("safety_gates", {})
        assert gates.get("approved_for_paper") == []
        assert gates.get("safe_to_enable_trading") is False


# ── C42: Data quality ────────────────────────────────────────────────────────

class TestDataQuality:
    def test_report_exists(self):
        report = _load_json("reports/data_quality_audit.json")
        assert report is not None

    def test_28_eligible_symbols(self):
        report = _load_json("reports/data_quality_audit.json")
        if report is None:
            pytest.skip("Report not found")
        assert report["n_eligible_symbols"] == 28

    def test_common_cutoff_is_actual_minimum_latest_bar_second_block(self):
        report = _load_json("reports/data_quality_audit.json")
        if report is None:
            pytest.skip("Report not found")
        latest = [item["last_ts"] for item in report["per_symbol"] if "last_ts" in item]
        assert latest
        assert report["common_cutoff_ts"] == min(latest)

    def test_excluded_symbols_reported(self):
        report = _load_json("reports/data_quality_audit.json")
        if report is None:
            pytest.skip("Report not found")
        assert "SEI" in report.get("excluded_symbols", [])

    def test_no_returns_in_report(self):
        report = _load_json("reports/data_quality_audit.json")
        if report is None:
            pytest.skip("Report not found")
        keys = _collect_keys(report)
        assert not keys & {"return", "returns", "pnl", "price"}


# ── C43: Dashboard ──────────────────────────────────────────────────────────

class TestDashboard:
    def test_dashboard_exists(self):
        d = _load_json("reports/research_state_dashboard.json")
        assert d is not None

    def test_safety_gates_closed(self):
        d = _load_json("reports/research_state_dashboard.json")
        if d is None:
            pytest.skip("Dashboard not found")
        gates = d["safety_gates"]
        assert gates["approved_for_paper"] == []
        assert gates["eligible_for_paper"] is False
        assert gates["safe_to_enable_trading"] is False
        assert gates["ready_for_combo_backtest"] is False

    def test_approved_and_candidate_zero(self):
        d = _load_json("reports/research_state_dashboard.json")
        if d is None:
            pytest.skip("Dashboard not found")
        assert d["registry_status"]["approved"] == 0
        assert d["registry_status"]["candidate"] == 0

    def test_no_returns_in_dashboard(self):
        d = _load_json("reports/research_state_dashboard.json")
        if d is None:
            pytest.skip("Dashboard not found")
        keys = _collect_keys(d)
        assert not keys & FORBIDDEN

    def test_cohort_a_28_signals(self):
        d = _load_json("reports/research_state_dashboard.json")
        if d is None:
            pytest.skip("Dashboard not found")
        assert d["cohort_a"]["signal_count"] == 28

    def test_md_exists(self):
        dashboard = _load_json("reports/research_state_dashboard.json")
        assert Path(f"docs/research_state_dashboard_{dashboard['generation_date']}.md").exists()
