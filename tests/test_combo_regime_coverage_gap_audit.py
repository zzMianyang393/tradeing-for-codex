"""Tests for combo_regime_coverage_gap_audit.py."""

from __future__ import annotations

import pytest

from combo_regime_coverage_gap_audit import analyze_coverage
from factor_regime_compatibility_matrix import get_matrix


class TestAnalyzeCoverage:
    def test_all_regimes_covered(self):
        matrix = get_matrix()
        result = analyze_coverage(matrix)
        for regime in ["趋势上行", "趋势下行", "高波动转换", "震荡"]:
            assert regime in result["regime_coverage"]
            assert result["regime_coverage"][regime]["n_directional"] >= 1

    def test_no_blank_regimes(self):
        matrix = get_matrix()
        result = analyze_coverage(matrix)
        assert len(result["blank_regimes"]) == 0

    def test_overlap_pairs_exist(self):
        matrix = get_matrix()
        result = analyze_coverage(matrix)
        assert len(result["overlap_pairs"]) >= 2

    def test_directional_factors_exist(self):
        matrix = get_matrix()
        result = analyze_coverage(matrix)
        for regime, info in result["regime_coverage"].items():
            assert isinstance(info["directional_factors"], list)
