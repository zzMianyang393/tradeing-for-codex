"""Strategy feature pool: schema and generator for combo research layer.

Reads from:
  - reports/research_approval_registry.json
  - reports/strategy_preflight_review.json

Generates a feature pool where rejected strategies can re-enter as
weak signals, context labels, or risk filters — but NEVER as standalone
strategies or paper-eligible instruments.

This is a RESEARCH LAYER tool.  It does NOT:
  - Create trading strategies
  - Approve anything for paper trading
  - Connect to runner.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


COMBO_BLOCKED_REJECTED_IDS = {
    "pairs_walk_forward": "No pair passed strict formation/OOS/FDR gates.",
    "spot_perp_basis": "Cost-friction failure: spread edge cannot cover four-leg execution.",
    "positive_funding_carry": "Cost-friction failure: no formation event clears four-leg carry cost.",
    "btc_alt_lead_lag": "High-turnover short-horizon edge is negative after cost.",
    "okx_futures_calendar_spread": "Cost-friction failure: four-leg calendar spread audit failed.",
    "utc_session_breakout_family": "High-turnover 15m breakout family failed after cost.",
    "regime_component_shared_capital_combo": "Shared-capital four-sleeve baseline failed return, drawdown, and fold-stability gates.",
}

CONTEXT_REJECTED_IDS = {
    "relative_strength_persistence": ["oos_decay"],
    "btc_trend_pullback": ["negative_formation_edge"],
    "vol_compression_breakout": ["insufficient_events"],
    "funding_term_carry": ["funding_overheat_context", "cost_friction_failed_as_strategy"],
    "funding_oi_time_corrected": ["timing_corrected_no_edge"],
    "daily_low_turnover_momentum": ["insufficient_events"],
    "daily_ma_alignment": ["insufficient_events", "no_oos_entries"],
    "daily_williams_r_range_reversion": [
        "range_oversold_context",
        "negative_in_formation_and_oos",
        "concentration_risk",
        "not_directional_without_new_evidence",
    ],
}

RISK_FILTER_REJECTED_IDS = {
    "multi_coin_funding_crowding": ["funding_crowding_risk"],
    "range_regime_funding_extreme": ["funding_extreme_risk"],
    "daily_oi_independent_change": ["meta_only_oi_leverage"],
    "range_regime_mean_reversion_family": ["range_false_breakout_risk"],
    "daily_atr_expansion_breakout": [
        "breakout_failure_risk",
        "oos_negative_after_cost",
        "concentration_risk",
    ],
    "daily_volume_confirmed_breakout": [
        "volume_breakout_failure_risk",
        "negative_in_formation_and_oos",
        "concentration_risk",
    ],
}

DIRECTIONAL_REJECTED_IDS = {
    "donchian_atr_trend_baseline": [
        "regime_conditioned_rejected",
        "requires_regime_gate",
        "trend_direction_only",
        "oos_declared_compatible_negative",
    ],
    "daily_bb_mean_revert": [
        "regime_conditioned_rejected",
        "requires_regime_gate",
        "range_only",
        "insufficient_declared_compatible_events",
    ],
    "daily_rsi_mean_revert": [
        "regime_conditioned_candidate",
        "requires_regime_gate",
        "downtrend_rebound_only",
        "posthoc_semantic_repair_requires_future_oos",
    ],
    "daily_trend_pullback": [
        "regime_conditioned_rejected",
        "requires_regime_gate",
        "trend_up_pullback_only",
        "oos_declared_compatible_negative",
    ],
    "4h_ema_crossover": [
        "regime_conditioned_candidate",
        "requires_regime_gate",
        "conditional_only",
        "trend_down_short_subsignal",
    ],
    "daily_parabolic_sar_trend": [
        "oos_positive_but_concentrated",
        "requires_concentration_penalty",
        "trend_direction_only",
        "not_standalone",
    ],
}


@dataclass(frozen=True)
class FeatureEntry:
    feature_id: str
    source_research_id: str
    source_status: str
    feature_role: str  # directional_weak_signal / context_label / risk_filter_candidate / blocked
    allowed_in_combo_research: bool
    allowed_as_standalone_strategy: bool  # always False
    eligible_for_paper: bool  # always False
    block_reasons: list[str]
    evidence_paths: list[str]
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_feature_pool(
    registry: dict,
    preflight: dict,
) -> list[FeatureEntry]:
    """Generate feature pool from registry and preflight review."""

    records = registry.get("records", [])
    record_map = {r["research_id"]: r for r in records}

    # Preflight reviews
    preflight_reviews = {r["strategy_id"]: r for r in preflight.get("reviews", [])}

    features: list[FeatureEntry] = []

    for record in records:
        rid = record["research_id"]
        status = record.get("status", "unknown")
        evidence = record.get("evidence_paths", [])

        # Determine feature role
        role, reasons, tags = _classify_feature(rid, status, record, preflight_reviews.get(rid, {}))

        features.append(FeatureEntry(
            feature_id=f"feat_{rid}",
            source_research_id=rid,
            source_status=status,
            feature_role=role,
            allowed_in_combo_research=role != "blocked",
            allowed_as_standalone_strategy=False,
            eligible_for_paper=False,
            block_reasons=reasons,
            evidence_paths=evidence,
            tags=tags,
        ))

    return features


def _classify_feature(
    rid: str,
    status: str,
    record: dict,
    preflight: dict,
) -> tuple[str, list[str], list[str]]:
    """Classify a research record into a feature role."""

    reasons: list[str] = []
    tags: list[str] = []

    # ── Hard blocks ──────────────────────────────────────────────────────

    if status == "invalid":
        return "blocked", ["Invalid research: data/timing issues."], []

    if status == "risk_blocked":
        return "blocked", ["Risk blocked: grid/martingale/locking family."], []

    if status == "data_blocked":
        return "blocked", ["Data blocked: no free reproducible data."], []

    # ── Check preflight for additional blocks ────────────────────────────

    pf_status = preflight.get("status", "")
    if pf_status == "risk_blocked":
        return "blocked", ["Preflight: risk blocked."], []
    if pf_status == "data_blocked":
        return "blocked", ["Preflight: data blocked."], []

    # ── Special cases ────────────────────────────────────────────────────

    if rid in COMBO_BLOCKED_REJECTED_IDS:
        return "blocked", [COMBO_BLOCKED_REJECTED_IDS[rid]], ["feature_pool_blocked"]

    if rid in CONTEXT_REJECTED_IDS:
        return "context_label", [], CONTEXT_REJECTED_IDS[rid]

    if rid in RISK_FILTER_REJECTED_IDS:
        return "risk_filter_candidate", [], RISK_FILTER_REJECTED_IDS[rid]

    if rid in DIRECTIONAL_REJECTED_IDS:
        return "directional_weak_signal", [], DIRECTIONAL_REJECTED_IDS[rid]

    # OI/leverage: only context_label or risk_filter_candidate.
    if rid in ("oi_divergence_signal", "oi_extreme_crowding", "leverage_ratio_reversal",
               "daily_oi_independent_change"):
        return "risk_filter_candidate", [], ["meta_only_oi_leverage"]

    # ── Status-based classification ──────────────────────────────────────

    if status == "rejected":
        return "context_label", ["Rejected research needs explicit reuse mapping before directional use."], [
            "rejected_single_strategy",
            "needs_manual_combo_mapping",
        ]

    if status == "frozen":
        return "blocked", ["Frozen: insufficient data or ML overfitting risk."], []

    if status == "meta_only":
        return "context_label", [], ["meta_only"]

    # Default
    return "blocked", [f"Unknown status: {status}"], []


# ── Validation ───────────────────────────────────────────────────────────────

def validate_feature_pool(features: list[FeatureEntry]) -> list[str]:
    """Validate the feature pool against mandatory rules.  Returns list of violations."""
    violations: list[str] = []

    for f in features:
        # allowed_as_standalone_strategy must be False
        if f.allowed_as_standalone_strategy:
            violations.append(f"{f.feature_id}: allowed_as_standalone_strategy must be False")

        # eligible_for_paper must be False
        if f.eligible_for_paper:
            violations.append(f"{f.feature_id}: eligible_for_paper must be False")

        # invalid must be blocked
        if f.source_status == "invalid" and f.feature_role != "blocked":
            violations.append(f"{f.feature_id}: invalid must be blocked")

        # risk_blocked must not be allowed_in_combo_research
        if f.source_status == "risk_blocked" and f.allowed_in_combo_research:
            violations.append(f"{f.feature_id}: risk_blocked must not be allowed_in_combo_research")

    return violations


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build strategy feature pool.")
    p.add_argument("--registry", type=Path, default=Path("reports/research_approval_registry.json"))
    p.add_argument("--preflight", type=Path, default=Path("reports/strategy_preflight_review.json"))
    p.add_argument("--out", type=Path, default=Path("reports/strategy_feature_pool.json"))
    args = p.parse_args(argv)

    registry = load_json(args.registry)
    preflight = load_json(args.preflight) or {}

    if not registry:
        print("ERROR: Cannot load registry")
        return 1

    features = build_feature_pool(registry, preflight)
    violations = validate_feature_pool(features)

    # Aggregate
    from collections import Counter
    role_counts = Counter(f.feature_role for f in features)
    status_counts = Counter(f.source_status for f in features)

    output = {
        "pool_type": "strategy_feature_pool",
        "generation_date": "2026-07-13",
        "n_features": len(features),
        "role_counts": dict(role_counts),
        "status_counts": dict(status_counts),
        "violations": violations,
        "safety_gates": {
            "allowed_as_standalone_strategy_all_false": all(not f.allowed_as_standalone_strategy for f in features),
            "eligible_for_paper_all_false": all(not f.eligible_for_paper for f in features),
        },
        "features": [f.to_dict() for f in features],
        "methodology_notes": [
            "Feature pool is a RESEARCH LAYER, not a strategy layer.",
            "No feature is allowed as standalone strategy or paper-eligible.",
            "Invalid/risk_blocked/data_blocked features are blocked.",
            "OI/leverage features can only be context_label or risk_filter_candidate.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")

    if violations:
        print(f"\nVIOLATIONS ({len(violations)}):")
        for v in violations:
            print(f"  {v}")

    print(f"\nFeatures: {len(features)}")
    for role, count in sorted(role_counts.items()):
        print(f"  {role}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
