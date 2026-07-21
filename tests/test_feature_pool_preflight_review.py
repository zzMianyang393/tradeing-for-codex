"""Tests for feature_pool_preflight_review.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from feature_pool_preflight_review import review_feature_pool


def _make_pool(features: list[dict]) -> dict:
    return {
        "features": features,
        "safety_gates": {
            "eligible_for_paper_all_false": True,
            "allowed_as_standalone_strategy_all_false": True,
        },
    }


class TestReviewFeaturePool:
    def test_directional_group(self):
        pool = _make_pool([
            {"feature_id": "f1", "source_research_id": "r1", "source_status": "rejected",
             "feature_role": "directional_weak_signal", "tags": [], "block_reasons": []}
        ])
        result = review_feature_pool(pool)
        assert len(result["groups"]["directional_feature_candidates"]) == 1

    def test_context_group(self):
        pool = _make_pool([
            {"feature_id": "f1", "source_research_id": "r1", "source_status": "meta_only",
             "feature_role": "context_label", "tags": [], "block_reasons": []}
        ])
        result = review_feature_pool(pool)
        assert len(result["groups"]["context_label_candidates"]) == 1

    def test_risk_filter_group(self):
        pool = _make_pool([
            {"feature_id": "f1", "source_research_id": "r1", "source_status": "rejected",
             "feature_role": "risk_filter_candidate", "tags": [], "block_reasons": []}
        ])
        result = review_feature_pool(pool)
        assert len(result["groups"]["risk_filter_candidates"]) == 1

    def test_blocked_group(self):
        pool = _make_pool([
            {"feature_id": "f1", "source_research_id": "r1", "source_status": "invalid",
             "feature_role": "blocked", "tags": [], "block_reasons": ["invalid"]}
        ])
        result = review_feature_pool(pool)
        assert len(result["groups"]["blocked_features"]) == 1

    def test_hard_blocked_cost_failure_is_blocked_even_if_role_is_directional(self):
        pool = _make_pool([
            {"feature_id": "feat_spot_perp_basis", "source_research_id": "spot_perp_basis", "source_status": "rejected",
             "feature_role": "directional_weak_signal", "tags": [], "block_reasons": []}
        ])
        result = review_feature_pool(pool)
        assert len(result["groups"]["directional_feature_candidates"]) == 0
        assert len(result["groups"]["blocked_features"]) == 1

    def test_no_oos_demoted_to_context(self):
        pool = _make_pool([
            {"feature_id": "f1", "source_research_id": "r1", "source_status": "rejected",
             "feature_role": "directional_weak_signal", "tags": ["no_oos_entries"], "block_reasons": []}
        ])
        result = review_feature_pool(pool)
        assert len(result["groups"]["directional_feature_candidates"]) == 0
        assert len(result["groups"]["context_label_candidates"]) == 1
        assert result["groups"]["context_label_candidates"][0]["demoted_to_context"]

    def test_concentration_penalty_flag(self):
        pool = _make_pool([
            {"feature_id": "f1", "source_research_id": "r1", "source_status": "rejected",
             "feature_role": "directional_weak_signal", "tags": ["concentration_risk"], "block_reasons": []}
        ])
        result = review_feature_pool(pool)
        entry = result["groups"]["directional_feature_candidates"][0]
        assert entry["requires_concentration_penalty"]

    def test_safety_gates(self):
        pool = _make_pool([])
        result = review_feature_pool(pool)
        assert result["safety_gates"]["approved_for_paper"] == []
        assert result["safety_gates"]["safe_to_enable_trading"] is False

    def test_empty_pool(self):
        pool = _make_pool([])
        result = review_feature_pool(pool)
        assert result["n_features"] == 0
        assert all(v == 0 for v in result["group_counts"].values())
