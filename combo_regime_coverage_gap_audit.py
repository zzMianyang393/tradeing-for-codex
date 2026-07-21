"""Combo regime coverage gap audit: identify regime states without directional factors.

Uses C18-C21 outputs to answer:
  - Which regime states have at least one directional weak factor
  - Which states only have context/risk filter (no directional)
  - Which states are completely blank
  - Which states have same-direction overlap (duplicate exposure risk)

Coverage status logic:
  - blank: no directional factor declares this regime
  - context_only: only context/risk factors, no directional
  - covered: 1-2 directional factors (no same-direction pair)
  - same_direction_overlap: >= 2 factors with same_direction overlap type in this regime

This is an OBSERVATION-ONLY audit.  It does NOT create trading rules.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from factor_regime_compatibility_matrix import (
    get_matrix,
    FactorRegimeEntry,
    compute_dedirected_overlaps,
)


ALL_REGIMES = {"趋势上行", "趋势下行", "高波动转换", "震荡"}


def analyze_coverage(matrix: list[FactorRegimeEntry]) -> dict[str, Any]:
    """Analyze which regimes are covered by directional factors."""

    regime_directional: dict[str, list[str]] = defaultdict(list)
    regime_context: dict[str, list[str]] = defaultdict(list)
    regime_risk: dict[str, list[str]] = defaultdict(list)

    for entry in matrix:
        for regime in entry.declared_regimes:
            if entry.allowed_role == "directional_weak_signal":
                regime_directional[regime].append(entry.factor_id)
            elif entry.allowed_role == "context_only":
                regime_context[regime].append(entry.factor_id)
            elif entry.allowed_role == "risk_filter_only":
                regime_risk[regime].append(entry.factor_id)

    # Dedirected overlaps — classify by type
    overlaps = compute_dedirected_overlaps(matrix)
    same_dir_pairs: set[tuple[str, str]] = set()
    opp_dir_pairs: set[tuple[str, str]] = set()
    semantic_pairs: set[tuple[str, str]] = set()
    for o in overlaps:
        pair = tuple(sorted([o["factor_a"], o["factor_b"]]))
        if o["overlap_type"] == "same_direction":
            same_dir_pairs.add(pair)
        elif o["overlap_type"] == "opposite_direction":
            opp_dir_pairs.add(pair)
        else:
            semantic_pairs.add(pair)

    # Coverage analysis
    coverage: dict[str, dict] = {}
    for regime in ALL_REGIMES:
        directional = regime_directional.get(regime, [])
        context = regime_context.get(regime, [])
        risk = regime_risk.get(regime, [])

        # Classify overlaps among this regime's directional factors
        same_dir_risks: list[str] = []
        opp_dir_risks: list[str] = []
        semantic_risks: list[str] = []
        for i, fa in enumerate(directional):
            for fb in directional[i+1:]:
                pair = tuple(sorted([fa, fb]))
                if pair in same_dir_pairs:
                    same_dir_risks.extend([fa, fb])
                elif pair in opp_dir_pairs:
                    opp_dir_risks.extend([fa, fb])
                elif pair in semantic_pairs:
                    semantic_risks.extend([fa, fb])

        if not directional:
            status = "blank"
        elif same_dir_risks:
            status = "same_direction_duplicate_risk"
        elif opp_dir_risks:
            status = "opposite_direction_conflict_risk"
        elif semantic_risks:
            status = "semantic_similarity_only"
        else:
            status = "covered"

        coverage[regime] = {
            "status": status,
            "directional_factors": directional,
            "context_factors": context,
            "risk_filter_factors": risk,
            "n_directional": len(directional),
            "same_direction_duplicate_risk_factors": sorted(set(same_dir_risks)),
            "opposite_direction_conflict_factors": sorted(set(opp_dir_risks)),
            "semantic_similarity_factors": sorted(set(semantic_risks)),
        }

    return {
        "regime_coverage": coverage,
        "overlap_pairs": overlaps,
        "blank_regimes": [r for r, c in coverage.items() if c["status"] == "blank"],
        "same_direction_duplicate_regimes": [r for r, c in coverage.items() if c["status"] == "same_direction_duplicate_risk"],
        "opposite_direction_conflict_regimes": [r for r, c in coverage.items() if c["status"] == "opposite_direction_conflict_risk"],
        "semantic_similarity_regimes": [r for r, c in coverage.items() if c["status"] == "semantic_similarity_only"],
        "covered_regimes": [r for r, c in coverage.items() if c["status"] == "covered"],
        "context_only_regimes": [r for r, c in coverage.items() if c["status"] == "context_only"],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Combo regime coverage gap audit.")
    p.add_argument("--out", type=Path, default=Path("reports/combo_regime_coverage_gap_audit.json"))
    args = p.parse_args(argv)

    matrix = get_matrix()
    analysis = analyze_coverage(matrix)

    output = {
        "audit_type": "combo_regime_coverage_gap",
        "audit_date": "2026-07-13",
        "observation_only": True,
        "n_factors": len(matrix),
        "n_regimes": len(ALL_REGIMES),
        **analysis,
        "methodology_notes": [
            "Coverage based on pre-registered factor-regime compatibility matrix.",
            "Blank = no factor declares this regime as applicable.",
            "same_direction_overlap = >= 2 factors with same_direction overlap type.",
            "Overlaps are dedirected (no A-B / B-A duplication).",
            "No trading rules created.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")

    for regime, info in analysis["regime_coverage"].items():
        print(f"  {regime}: {info['status']} (directional={info['n_directional']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
