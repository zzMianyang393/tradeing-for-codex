"""Combo research safety gate tests.

Verifies that:
  - Combo research code does not import or call runner.py trading entry
  - Feature pool items cannot be eligible_for_paper=true
  - grid_martingale_locking_family cannot enter any candidate pool
  - Invalid research can only be blocked
  - Feature pool is a research layer, not a strategy layer
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strategy_feature_pool import build_feature_pool, validate_feature_pool


def _load_registry() -> dict:
    path = Path("reports/research_approval_registry.json")
    if not path.exists():
        pytest.skip("Registry not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_preflight() -> dict:
    path = Path("reports/strategy_preflight_review.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_feature_pool() -> dict:
    path = Path("reports/strategy_feature_pool.json")
    if not path.exists():
        pytest.skip("Feature pool not found")
    return json.loads(path.read_text(encoding="utf-8"))


class TestComboSafetyGates:
    def test_approved_for_paper_empty(self):
        """approved_for_paper must remain empty."""
        registry = _load_registry()
        assert registry.get("approved_for_paper", []) == []

    def test_safe_to_enable_trading_false(self):
        """safe_to_enable_trading must be false."""
        registry = _load_registry()
        assert registry.get("safe_to_enable_trading", True) is False

    def test_no_feature_eligible_for_paper(self):
        """No feature in the pool can have eligible_for_paper=true."""
        pool = _load_feature_pool()
        for f in pool.get("features", []):
            assert f["eligible_for_paper"] is False, f"{f['feature_id']} has eligible_for_paper=True"

    def test_no_feature_allowed_as_standalone(self):
        """No feature can be allowed as standalone strategy."""
        pool = _load_feature_pool()
        for f in pool.get("features", []):
            assert f["allowed_as_standalone_strategy"] is False, \
                f"{f['feature_id']} has allowed_as_standalone_strategy=True"

    def test_grid_martingale_not_in_any_pool(self):
        """grid_martingale_locking_family must be blocked, not in directional/context/risk."""
        pool = _load_feature_pool()
        for f in pool.get("features", []):
            if "grid" in f["source_research_id"] or "martingale" in f["source_research_id"]:
                assert f["feature_role"] == "blocked", \
                    f"{f['feature_id']} should be blocked, got {f['feature_role']}"

    def test_invalid_only_blocked(self):
        """Invalid research can only have feature_role=blocked."""
        pool = _load_feature_pool()
        for f in pool.get("features", []):
            if f["source_status"] == "invalid":
                assert f["feature_role"] == "blocked", \
                    f"{f['feature_id']} (invalid) should be blocked, got {f['feature_role']}"

    def test_risk_blocked_not_in_combo(self):
        """Risk_blocked research must not be allowed_in_combo_research."""
        pool = _load_feature_pool()
        for f in pool.get("features", []):
            if f["source_status"] == "risk_blocked":
                assert f["allowed_in_combo_research"] is False, \
                    f"{f['feature_id']} (risk_blocked) should not be allowed_in_combo_research"

    def test_feature_pool_violations_empty(self):
        """The feature pool should have no validation violations."""
        pool = _load_feature_pool()
        violations = pool.get("violations", [])
        assert violations == [], f"Violations found: {violations}"

    def test_feature_pool_is_research_layer(self):
        """Feature pool metadata must confirm it is a research layer."""
        pool = _load_feature_pool()
        notes = pool.get("methodology_notes", [])
        assert any("RESEARCH LAYER" in n for n in notes), "Missing 'RESEARCH LAYER' in methodology notes"

    def test_runner_not_imported_by_combo_modules(self):
        """Combo research modules should not import runner."""
        combo_modules = [
            "strategy_feature_pool.py",
            "feature_pool_preflight_review.py",
            "combo_feature_timeseries.py",
            "combo_research_matrix.py",
            "combo_matrix_quality_review.py",
            "regime_bucket_combo_coverage.py",
            "downtrend_rebound_combo_hypothesis_audit.py",
            "downtrend_rebound_event_time_filter_audit.py",
            "downtrend_rebound_exposure_concentration_audit.py",
            "downtrend_rebound_capital_constrained_simulator.py",
            "donchian_uptrend_capital_constrained_simulation.py",
            "two_regime_shared_capital_combo_simulation.py",
            "ema_short_downtrend_capital_constrained_simulation.py",
            "downtrend_bidirectional_combo_simulation.py",
            "downtrend_bidirectional_drawdown_anatomy_audit.py",
            "downtrend_bidirectional_fixed_risk_budget_simulation.py",
            "downtrend_bidirectional_future_validation.py",
            "downtrend_bidirectional_future_anatomy_audit.py",
            "regime_component_walk_forward_audit.py",
            "range_regime_structure_audit.py",
            "range_regime_v2_walk_forward_audit.py",
            "low_volatility_drift_breakout_audit.py",
            "low_volatility_drift_fixed_risk_audit.py",
            "prospective_candidate_registry.py",
            "prospective_data_clock.py",
            "uptrend_regime_structure_audit.py",
            "uptrend_breadth_context_audit.py",
            "historical_fold_universe_audit.py",
            "persistent_uptrend_entry_batch_audit.py",
            "weak_component_complementarity_audit.py",
            "restricted_weak_pair_combo_simulation.py",
            "restricted_combo_drawdown_anatomy_audit.py",
            "daily_volume_shock_reversal_preflight.py",
            "daily_volume_shock_reversal_audit.py",
            "volume_shock_short_complementarity_audit.py",
            "weekly_cross_sectional_momentum_audit.py",
            "weekly_weakest_short_complementarity_audit.py",
            "weekly_range_cross_sectional_reversal_preflight.py",
            "weekly_range_microtrend_continuation_audit.py",
            "range_microtrend_long_complementarity_audit.py",
            "funding_term_price_alignment_preflight.py",
            "funding_term_price_alignment_audit.py",
            "high_positive_funding_long_risk_filter_audit.py",
            "oi_state_weak_signal_overlap_preflight.py",
            "prospective_shadow_signal_ledger.py",
            "prospective_signal_interaction_audit.py",
            "prospective_signal_conflict_arbitrator.py",
            "prospective_legacy_weak_factor_preflight.py",
            "prospective_second_batch_factor_preflight.py",
        ]
        for mod_name in combo_modules:
            path = Path(mod_name)
            if path.exists():
                content = path.read_text(encoding="utf-8")
                # Check for direct runner imports
                assert "from runner import" not in content, f"{mod_name} imports runner"
                assert "import runner" not in content, f"{mod_name} imports runner"

    def test_combo_watchlist_items_remain_non_executable(self):
        path = Path("reports/prospective_candidate_registry.json")
        if not path.exists():
            pytest.skip("Prospective registry not found")
        registry = json.loads(path.read_text(encoding="utf-8"))
        combo_items = [item for item in registry.get("watchlist", []) if str(item.get("candidate_id", "")).startswith("combo::")]
        assert combo_items
        for item in combo_items:
            assert item["status"] == "combo_watchlist_strict_gate_failed"
            assert item["allowed_in_combo_backtest"] is False

    def test_restricted_combo_report_does_not_open_global_gates(self):
        path = Path("reports/restricted_weak_pair_combo_simulation.json")
        if not path.exists():
            pytest.skip("Restricted combo report not found")
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["frozen_observed_combo_candidates"] == []
        assert report["safety_gates"] == {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        }

    def test_posthoc_volume_pair_watchlist_cannot_authorize_combo_simulation(self):
        path = Path("reports/volume_shock_short_complementarity_audit.json")
        if not path.exists():
            pytest.skip("Volume complementarity report not found")
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["restricted_combo_simulation_authorized"] is False
        for item in report["pairs"].values():
            assert item["eligible_for_restricted_combo_simulation"] is False

    def test_posthoc_weekly_short_cannot_authorize_combo_simulation(self):
        path = Path("reports/weekly_weakest_short_complementarity_audit.json")
        if not path.exists():
            pytest.skip("Weekly complementarity report not found")
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["restricted_combo_simulation_authorized"] is False
        assert report["safety_gates"] == {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        }
        for item in report["pairs"].values():
            assert item["eligible_for_restricted_combo_simulation"] is False

    def test_posthoc_range_long_cannot_authorize_combo_simulation(self):
        path = Path("reports/range_microtrend_long_complementarity_audit.json")
        if not path.exists():
            pytest.skip("Range complementarity report not found")
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["restricted_combo_simulation_authorized"] is False
        assert report["safety_gates"] == {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        }
        for item in report["pairs"].values():
            assert item["eligible_for_restricted_combo_simulation"] is False
