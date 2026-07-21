"""Tests for strategy_feature_pool.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strategy_feature_pool import (
    FeatureEntry,
    build_feature_pool,
    validate_feature_pool,
)


# ── Mock data ────────────────────────────────────────────────────────────────

def _make_registry(records: list[dict]) -> dict:
    return {
        "records": records,
        "approved_for_paper": [],
        "safe_to_enable_trading": False,
    }


def _make_preflight(reviews: list[dict]) -> dict:
    return {"reviews": reviews}


# ── build_feature_pool ───────────────────────────────────────────────────────

class TestBuildFeaturePool:
    def test_basic(self):
        registry = _make_registry([
            {"research_id": "test1", "status": "rejected", "evidence_paths": ["r1.json"]},
        ])
        features = build_feature_pool(registry, {})
        assert len(features) == 1
        assert features[0].feature_id == "feat_test1"

    def test_invalid_is_blocked(self):
        registry = _make_registry([
            {"research_id": "funding_oi_joint_original", "status": "invalid", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "blocked"
        assert not features[0].allowed_in_combo_research

    def test_risk_blocked_is_blocked(self):
        registry = _make_registry([
            {"research_id": "grid_martingale_locking_family", "status": "risk_blocked", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "blocked"
        assert not features[0].allowed_in_combo_research

    def test_data_blocked_is_blocked(self):
        registry = _make_registry([
            {"research_id": "news_sentiment", "status": "data_blocked", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "blocked"

    def test_unmapped_rejected_defaults_to_context(self):
        registry = _make_registry([
            {"research_id": "unknown_rejected_rule", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "context_label"
        assert features[0].allowed_in_combo_research
        assert "needs_manual_combo_mapping" in features[0].tags

    def test_meta_only_is_context(self):
        registry = _make_registry([
            {"research_id": "cross_time_stability", "status": "meta_only", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "context_label"


# ── Special cases ────────────────────────────────────────────────────────────

class TestSpecialCases:
    def test_oi_leverage_is_risk_filter(self):
        registry = _make_registry([
            {"research_id": "oi_divergence_signal", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "risk_filter_candidate"
        assert "meta_only_oi_leverage" in features[0].tags

    def test_daily_bb_has_regime_conditioned_rejection_tags(self):
        registry = _make_registry([
            {"research_id": "daily_bb_mean_revert", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "directional_weak_signal"
        assert "regime_conditioned_rejected" in features[0].tags
        assert "range_only" in features[0].tags
        assert "insufficient_declared_compatible_events" in features[0].tags

    def test_donchian_has_regime_conditioned_rejection_tags(self):
        registry = _make_registry([
            {"research_id": "donchian_atr_trend_baseline", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "directional_weak_signal"
        assert "regime_conditioned_rejected" in features[0].tags
        assert "trend_direction_only" in features[0].tags
        assert "oos_declared_compatible_negative" in features[0].tags

    def test_ema_crossover_is_conditional_directional_feature(self):
        registry = _make_registry([
            {"research_id": "4h_ema_crossover", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "directional_weak_signal"
        assert "regime_conditioned_candidate" in features[0].tags
        assert "requires_regime_gate" in features[0].tags
        assert features[0].eligible_for_paper is False

    def test_cost_friction_arbitrage_is_blocked(self):
        registry = _make_registry([
            {"research_id": "spot_perp_basis", "status": "rejected", "evidence_paths": []},
            {"research_id": "okx_futures_calendar_spread", "status": "rejected", "evidence_paths": []},
            {"research_id": "utc_session_breakout_family", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert all(f.feature_role == "blocked" for f in features)
        assert all(not f.allowed_in_combo_research for f in features)

    def test_failed_shared_capital_combo_is_blocked_from_reuse(self):
        registry = _make_registry([
            {"research_id": "regime_component_shared_capital_combo", "status": "rejected", "evidence_paths": []},
        ])
        feature = build_feature_pool(registry, {})[0]
        assert feature.feature_role == "blocked"
        assert feature.allowed_in_combo_research is False

    def test_funding_term_carry_is_context_not_directional(self):
        registry = _make_registry([
            {"research_id": "funding_term_carry", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "context_label"
        assert "funding_overheat_context" in features[0].tags

    def test_range_mean_reversion_is_risk_filter(self):
        registry = _make_registry([
            {"research_id": "range_regime_mean_reversion_family", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "risk_filter_candidate"
        assert "range_false_breakout_risk" in features[0].tags

    def test_daily_ma_is_context(self):
        registry = _make_registry([
            {"research_id": "daily_ma_alignment", "status": "rejected", "evidence_paths": []},
        ])
        features = build_feature_pool(registry, {})
        assert features[0].feature_role == "context_label"
        assert "insufficient_events" in features[0].tags

    def test_latest_rejected_audits_have_explicit_combo_reuse_roles(self):
        registry = _make_registry([
            {"research_id": "daily_williams_r_range_reversion", "status": "rejected", "evidence_paths": []},
            {"research_id": "daily_parabolic_sar_trend", "status": "rejected", "evidence_paths": []},
            {"research_id": "daily_atr_expansion_breakout", "status": "rejected", "evidence_paths": []},
            {"research_id": "daily_volume_confirmed_breakout", "status": "rejected", "evidence_paths": []},
        ])
        by_id = {feature.source_research_id: feature for feature in build_feature_pool(registry, {})}

        assert by_id["daily_williams_r_range_reversion"].feature_role == "context_label"
        assert by_id["daily_parabolic_sar_trend"].feature_role == "directional_weak_signal"
        assert by_id["daily_atr_expansion_breakout"].feature_role == "risk_filter_candidate"
        assert by_id["daily_volume_confirmed_breakout"].feature_role == "risk_filter_candidate"
        for feature in by_id.values():
            assert feature.allowed_in_combo_research is True
            assert feature.allowed_as_standalone_strategy is False
            assert feature.eligible_for_paper is False
            assert "needs_manual_combo_mapping" not in feature.tags


# ── validate_feature_pool ────────────────────────────────────────────────────

class TestValidateFeaturePool:
    def test_no_violations_for_valid_pool(self):
        features = [
            FeatureEntry(
                feature_id="feat_test",
                source_research_id="test",
                source_status="rejected",
                feature_role="directional_weak_signal",
                allowed_in_combo_research=True,
                allowed_as_standalone_strategy=False,
                eligible_for_paper=False,
                block_reasons=[],
                evidence_paths=[],
            )
        ]
        violations = validate_feature_pool(features)
        assert violations == []

    def test_standalone_strategy_violation(self):
        features = [
            FeatureEntry(
                feature_id="feat_bad",
                source_research_id="bad",
                source_status="rejected",
                feature_role="directional_weak_signal",
                allowed_in_combo_research=True,
                allowed_as_standalone_strategy=True,
                eligible_for_paper=False,
                block_reasons=[],
                evidence_paths=[],
            )
        ]
        violations = validate_feature_pool(features)
        assert any("allowed_as_standalone_strategy" in v for v in violations)

    def test_paper_eligible_violation(self):
        features = [
            FeatureEntry(
                feature_id="feat_bad",
                source_research_id="bad",
                source_status="rejected",
                feature_role="directional_weak_signal",
                allowed_in_combo_research=True,
                allowed_as_standalone_strategy=False,
                eligible_for_paper=True,
                block_reasons=[],
                evidence_paths=[],
            )
        ]
        violations = validate_feature_pool(features)
        assert any("eligible_for_paper" in v for v in violations)

    def test_invalid_not_blocked_violation(self):
        features = [
            FeatureEntry(
                feature_id="feat_bad",
                source_research_id="bad",
                source_status="invalid",
                feature_role="directional_weak_signal",
                allowed_in_combo_research=True,
                allowed_as_standalone_strategy=False,
                eligible_for_paper=False,
                block_reasons=[],
                evidence_paths=[],
            )
        ]
        violations = validate_feature_pool(features)
        assert any("invalid must be blocked" in v for v in violations)

    def test_risk_blocked_not_allowed_in_combo(self):
        features = [
            FeatureEntry(
                feature_id="feat_bad",
                source_research_id="bad",
                source_status="risk_blocked",
                feature_role="blocked",
                allowed_in_combo_research=True,
                allowed_as_standalone_strategy=False,
                eligible_for_paper=False,
                block_reasons=[],
                evidence_paths=[],
            )
        ]
        violations = validate_feature_pool(features)
        assert any("risk_blocked" in v for v in violations)
