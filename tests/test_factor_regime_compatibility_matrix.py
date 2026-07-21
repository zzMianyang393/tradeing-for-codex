"""Tests for factor_regime_compatibility_matrix.py."""

from __future__ import annotations

import pytest

from factor_regime_compatibility_matrix import get_matrix, COMPATIBILITY_MATRIX


class TestMatrixStructure:
    def test_minimum_factors(self):
        assert len(COMPATIBILITY_MATRIX) >= 7

    def test_unique_ids(self):
        ids = [e.factor_id for e in COMPATIBILITY_MATRIX]
        assert len(ids) == len(set(ids))

    def test_all_regimes_covered(self):
        all_regimes = set()
        for entry in COMPATIBILITY_MATRIX:
            all_regimes.update(entry.declared_regimes)
        assert "趋势上行" in all_regimes
        assert "趋势下行" in all_regimes
        assert "震荡" in all_regimes

    def test_allowed_roles_valid(self):
        valid_roles = {"directional_weak_signal", "context_only", "risk_filter_only"}
        for entry in COMPATIBILITY_MATRIX:
            assert entry.allowed_role in valid_roles

    def test_no_empty_declared_regimes(self):
        for entry in COMPATIBILITY_MATRIX:
            assert len(entry.declared_regimes) > 0


class TestOverlapPairs:
    def test_overlap_pairs_exist(self):
        pairs = []
        for entry in COMPATIBILITY_MATRIX:
            for overlap_id in entry.semantic_overlap_with:
                pairs.append((entry.factor_id, overlap_id))
        assert len(pairs) >= 2  # at least weekly and trend overlaps
