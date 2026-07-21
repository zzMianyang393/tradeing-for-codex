"""Factor-regime compatibility matrix: maps 7 shadow factors to regime labels.

Includes:
  - Versioned regime vocabulary mapping (REGIME_VOCABULARY_VERSION)
  - candidate_id <-> factor_id mapping
  - Standard regime label normalization
  - Dedirected overlap pairs (no A-B / B-A duplication)
  - Overlap classification: same_direction / opposite_direction / semantic_only

This is an OBSERVATION-ONLY mapping.  It does NOT:
  - Calculate returns
  - Generate signals
  - Modify factor definitions
  - Optimize parameters
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


# ── Regime vocabulary mapping (versioned) ────────────────────────────────────

REGIME_VOCABULARY_VERSION = "v1.0.0"

# Standard labels used by the combo layer
STANDARD_REGIMES = {"趋势上行", "趋势下行", "高波动转换", "震荡"}

# Maps raw/non-standard labels to standard labels.
# Unknown labels map to None — they must NOT be silently classified as compliant.
REGIME_VOCABULARY: dict[str, str | None] = {
    # Standard 4h labels
    "趋势上行": "趋势上行",
    "趋势下行": "趋势下行",
    "高波动转换": "高波动转换",
    "震荡": "震荡",
    # Factor-internal labels → standard mapping
    "low_volatility_drift_v2": "震荡",
    "downtrend": "趋势下行",
    "persistent_uptrend_over_10d_btc_aligned": "趋势上行",
    "mean_reverting_range_v2": "震荡",
    "cross_sectional_weakness_continuation": "趋势下行",
    "uptrend": "趋势上行",
    "range": "震荡",
    "volatile_transition": "高波动转换",
    # Aliases
    "trend_up": "趋势上行",
    "trend_down": "趋势下行",
    "range_bound": "震荡",
    "high_vol": "高波动转换",
}

# candidate_id (from ledger) → factor_id (in matrix)
CANDIDATE_TO_FACTOR: dict[str, str] = {
    "donchian_atr_trend_baseline": "donchian_atr_trend_baseline",
    "ema_continuation_short_downtrend_v1": "ema_continuation_short_downtrend_v1",
    "low_volatility_drift_bb_breakout_fixed_risk_v1": "low_volatility_drift_bb_breakout_fixed_risk_v1",
    "persistent_uptrend_ema20_reclaim_v1": "persistent_uptrend_ema20_reclaim_v1",
    "daily_volume_shock_reversal_v1_short": "daily_volume_shock_reversal_v1_short",
    "weekly_cross_sectional_momentum_v1_short": "weekly_cross_sectional_momentum_v1_short",
    "weekly_range_microtrend_continuation_v1_long": "weekly_range_microtrend_continuation_v1_long",
}

# Reverse mapping
FACTOR_TO_CANDIDATE: dict[str, str] = {v: k for k, v in CANDIDATE_TO_FACTOR.items()}


def normalize_regime(raw_label: str) -> str | None:
    """Map a raw regime label to a standard label.

    Returns None for unknown labels — caller must handle as missing/invalid.
    """
    return REGIME_VOCABULARY.get(raw_label)


def is_regime_known(raw_label: str) -> bool:
    """Check whether a raw label has a known mapping."""
    return raw_label in REGIME_VOCABULARY


# ── Factor-regime entry ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class FactorRegimeEntry:
    factor_id: str
    candidate_id: str
    declared_regimes: list[str]
    not_applicable_regimes: list[str]
    needs_btc_confirmation: bool
    time_granularity: str
    label_availability_delay: str
    allowed_role: str  # directional_weak_signal / context_only / risk_filter_only
    semantic_overlap_with: list[str]
    overlap_type: str  # same_direction / opposite_direction / semantic_only
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Fixed matrix (pre-registered, not derived from data) ────────────────────

COMPATIBILITY_MATRIX: list[FactorRegimeEntry] = [

    FactorRegimeEntry(
        factor_id="low_volatility_drift_bb_breakout_fixed_risk_v1",
        candidate_id="low_volatility_drift_bb_breakout_fixed_risk_v1",
        declared_regimes=["震荡"],
        not_applicable_regimes=["趋势上行", "趋势下行", "高波动转换"],
        needs_btc_confirmation=False,
        time_granularity="4h",
        label_availability_delay="4h (bar close + 4h)",
        allowed_role="directional_weak_signal",
        semantic_overlap_with=["daily_volume_shock_reversal_v1_short"],
        overlap_type="semantic_only",
        notes="BB breakout in range regime.",
    ),
    FactorRegimeEntry(
        factor_id="ema_continuation_short_downtrend_v1",
        candidate_id="ema_continuation_short_downtrend_v1",
        declared_regimes=["趋势下行"],
        not_applicable_regimes=["趋势上行", "震荡", "高波动转换"],
        needs_btc_confirmation=True,
        time_granularity="4h",
        label_availability_delay="4h",
        allowed_role="directional_weak_signal",
        semantic_overlap_with=[],
        overlap_type="semantic_only",
        notes="Short continuation in confirmed downtrend.",
    ),
    FactorRegimeEntry(
        factor_id="persistent_uptrend_ema20_reclaim_v1",
        candidate_id="persistent_uptrend_ema20_reclaim_v1",
        declared_regimes=["趋势上行"],
        not_applicable_regimes=["趋势下行", "震荡", "高波动转换"],
        needs_btc_confirmation=True,
        time_granularity="4h",
        label_availability_delay="4h",
        allowed_role="directional_weak_signal",
        semantic_overlap_with=["donchian_atr_trend_baseline"],
        overlap_type="same_direction",
        notes="Uptrend EMA20 reclaim. Same direction as Donchian trend.",
    ),
    FactorRegimeEntry(
        factor_id="daily_volume_shock_reversal_v1_short",
        candidate_id="daily_volume_shock_reversal_v1_short",
        declared_regimes=["高波动转换", "震荡"],
        not_applicable_regimes=["趋势上行", "趋势下行"],
        needs_btc_confirmation=False,
        time_granularity="daily",
        label_availability_delay="4h (regime) + daily (volume)",
        allowed_role="directional_weak_signal",
        semantic_overlap_with=["low_volatility_drift_bb_breakout_fixed_risk_v1"],
        overlap_type="semantic_only",
        notes="Volume shock reversal in range/volatile regimes.",
    ),
    FactorRegimeEntry(
        factor_id="weekly_cross_sectional_momentum_v1_short",
        candidate_id="weekly_cross_sectional_momentum_v1_short",
        declared_regimes=["趋势下行"],  # registry: cross_sectional_weakness_continuation
        not_applicable_regimes=["趋势上行", "震荡", "高波动转换"],
        needs_btc_confirmation=False,
        time_granularity="weekly",
        label_availability_delay="4h (regime) + weekly (momentum)",
        allowed_role="directional_weak_signal",
        semantic_overlap_with=["weekly_range_microtrend_continuation_v1_long"],
        overlap_type="opposite_direction",  # short vs long
        notes="Cross-sectional momentum short. Direction=short. Opposite of microtrend long.",
    ),
    FactorRegimeEntry(
        factor_id="weekly_range_microtrend_continuation_v1_long",
        candidate_id="weekly_range_microtrend_continuation_v1_long",
        declared_regimes=["震荡"],  # registry: mean_reverting_range_v2
        not_applicable_regimes=["趋势上行", "趋势下行", "高波动转换"],
        needs_btc_confirmation=False,
        time_granularity="weekly",
        label_availability_delay="4h (regime) + weekly (microtrend)",
        allowed_role="directional_weak_signal",
        semantic_overlap_with=["weekly_cross_sectional_momentum_v1_short"],
        overlap_type="opposite_direction",  # long vs short
        notes="Microtrend continuation long in range. Direction=long. Opposite of cross-sectional short.",
    ),
    FactorRegimeEntry(
        factor_id="donchian_atr_trend_baseline",
        candidate_id="donchian_atr_trend_baseline",
        declared_regimes=["趋势上行"],
        not_applicable_regimes=["趋势下行", "震荡", "高波动转换"],
        needs_btc_confirmation=False,
        time_granularity="daily",
        label_availability_delay="4h (regime) + daily (Donchian)",
        allowed_role="directional_weak_signal",
        semantic_overlap_with=["persistent_uptrend_ema20_reclaim_v1"],
        overlap_type="same_direction",
        notes="Donchian 55 breakout in uptrend. Same direction as EMA20 reclaim.",
    ),
]


def get_matrix() -> list[FactorRegimeEntry]:
    return list(COMPATIBILITY_MATRIX)


def get_entry_by_factor_id(factor_id: str) -> FactorRegimeEntry | None:
    for e in COMPATIBILITY_MATRIX:
        if e.factor_id == factor_id:
            return e
    return None


def get_entry_by_candidate_id(candidate_id: str) -> FactorRegimeEntry | None:
    factor_id = CANDIDATE_TO_FACTOR.get(candidate_id)
    if factor_id:
        return get_entry_by_factor_id(factor_id)
    return None


def compute_dedirected_overlaps(matrix: list[FactorRegimeEntry]) -> list[dict]:
    """Compute dedirected overlap pairs (no A-B / B-A duplication)."""
    seen: set[tuple[str, str]] = set()
    pairs: list[dict] = []

    for entry in matrix:
        for other_id in entry.semantic_overlap_with:
            key = tuple(sorted([entry.factor_id, other_id]))
            if key in seen:
                continue
            seen.add(key)

            other_entry = get_entry_by_factor_id(other_id)
            overlap_type = entry.overlap_type

            # Determine shared regimes
            shared = set(entry.declared_regimes) & set(other_entry.declared_regimes) if other_entry else set()

            pairs.append({
                "factor_a": key[0],
                "factor_b": key[1],
                "overlap_type": overlap_type,
                "shared_regimes": sorted(shared),
                "direction_conflict": overlap_type == "opposite_direction",
            })

    return pairs


def main(argv=None):
    p = argparse.ArgumentParser(description="Factor-regime compatibility matrix.")
    p.add_argument("--out", type=Path, default=Path("reports/factor_regime_compatibility_matrix.json"))
    args = p.parse_args(argv)

    matrix = get_matrix()
    overlaps = compute_dedirected_overlaps(matrix)

    output = {
        "matrix_type": "factor_regime_compatibility",
        "generation_date": "2026-07-13",
        "observation_only": True,
        "regime_vocabulary_version": REGIME_VOCABULARY_VERSION,
        "n_factors": len(matrix),
        "n_regimes": len(STANDARD_REGIMES),
        "standard_regimes": sorted(STANDARD_REGIMES),
        "regime_vocabulary": {k: v for k, v in sorted(REGIME_VOCABULARY.items())},
        "candidate_to_factor_mapping": CANDIDATE_TO_FACTOR,
        "matrix": [e.to_dict() for e in matrix],
        "overlap_pairs": overlaps,
        "overlap_summary": {
            "total_pairs": len(overlaps),
            "same_direction": sum(1 for o in overlaps if o["overlap_type"] == "same_direction"),
            "opposite_direction": sum(1 for o in overlaps if o["overlap_type"] == "opposite_direction"),
            "semantic_only": sum(1 for o in overlaps if o["overlap_type"] == "semantic_only"),
        },
        "methodology_notes": [
            "Matrix is pre-registered, not derived from data.",
            "Regime vocabulary is versioned; unknown labels map to None.",
            "Overlap pairs are dedirected (no A-B / B-A duplication).",
            "Overlap types: same_direction, opposite_direction, semantic_only.",
            "No returns calculated.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Factors: {len(matrix)}, Overlap pairs: {len(overlaps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
