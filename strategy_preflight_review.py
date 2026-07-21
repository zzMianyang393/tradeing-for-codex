"""Strategy preflight review: filter prototypes against risk constraints before coding.

Reads:
  - strategy_prototype_universe.py (prototypes)
  - reports/research_risk_map.json (cost/turnover constraints)
  - reports/research_approval_registry.json (rejected/invalid IDs)

Outputs per-prototype status:
  - eligible_for_research
  - meta_only
  - risk_blocked
  - data_blocked
  - duplicate_rejected
  - rejected_by_cost
  - rejected_by_turnover

This is a PLANNING tool.  It does NOT:
  - Create strategies
  - Approve anything for paper trading
  - Modify runner.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from strategy_prototype_universe import StrategyPrototype, get_prototypes


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def review_prototype(
    proto: StrategyPrototype,
    risk_map: dict,
    rejected_ids: set[str],
    invalid_ids: set[str],
) -> dict[str, Any]:
    """Determine the preflight status of a single prototype."""

    reasons: list[str] = []
    status = "eligible_for_research"

    # ── 0. Exact registry match → duplicate_rejected ─────────────────────
    if proto.strategy_id in rejected_ids or proto.strategy_id in invalid_ids:
        reasons.append(f"Prototype itself is already rejected/invalid: {proto.strategy_id}")
        status = "duplicate_rejected"

    # ── 1. Grid / martingale → risk_blocked ──────────────────────────────
    if proto.uses_grid_or_martingale:
        return {
            "strategy_id": proto.strategy_id,
            "status": "risk_blocked",
            "reasons": ["Grid/martingale/locking strategies are permanently blocked."],
        }

    # ── 2. HFT / orderbook / tick → data_blocked ─────────────────────────
    if proto.uses_hft_or_orderbook:
        return {
            "strategy_id": proto.strategy_id,
            "status": "data_blocked",
            "reasons": ["HFT/orderbook/tick data has no free reproducible history."],
        }

    # ── 3. External / news / macro data → data_blocked ───────────────────
    if proto.uses_external_data:
        return {
            "strategy_id": proto.strategy_id,
            "status": "data_blocked",
            "reasons": ["External/news/macro data has no free reproducible 365-day history."],
        }

    # ── 4. resembles_rejected → duplicate_rejected ──────────────────────
    if proto.resembles_rejected:
        overlap = [rid for rid in proto.resembles_rejected if rid in rejected_ids or rid in invalid_ids]
        if overlap:
            reasons.append(f"Resembles rejected/invalid: {', '.join(overlap)}")
        else:
            reasons.append(
                "Resembles rejected/invalid family labels pending registry match: "
                f"{', '.join(proto.resembles_rejected)}"
            )
        status = "duplicate_rejected"

    # ── 5. Cost floor check ──────────────────────────────────────────────
    cost_constraints = risk_map.get("cost_constraints", {})
    single_leg_rt = cost_constraints.get("single_market_round_trip_cost", 0.0016)
    four_leg_rt = cost_constraints.get("two_market_round_trip_cost", 0.0032)

    if proto.executed_legs >= 4:
        # Four-leg strategies must clear 0.32%
        # Estimate: if expected_events_per_month * cost > 10% of monthly return potential
        # For now, just flag if the strategy has high event frequency with 4 legs
        if proto.expected_events_per_month > 8:
            monthly_cost = proto.expected_events_per_month * four_leg_rt * 100
            if monthly_cost > 10:
                reasons.append(f"4-leg monthly cost {monthly_cost:.1f}% exceeds 10% threshold.")
                if status == "eligible_for_research":
                    status = "rejected_by_cost"

    # ── 6. OI/leverage family can only be meta_only (before turnover) ────
    if proto.family == "oi_leverage" and status not in ("risk_blocked", "data_blocked", "duplicate_rejected"):
        reasons.append("OI/leverage family: daily OI only, cannot be primary signal.")
        status = "meta_only"

    # ── 7. ML family → frozen (before turnover) ─────────────────────────
    if proto.family == "machine_learning" and status not in ("risk_blocked", "data_blocked", "duplicate_rejected"):
        reasons.append("ML family: overfitting risk, insufficient free data.")
        status = "frozen"

    # ── 8. Turnover check (after family overrides) ───────────────────────
    turnover = risk_map.get("turnover_constraints", {})
    thresholds = turnover.get("thresholds", {})
    min_hold = thresholds.get("min_hold_days", 3.0)
    max_events = thresholds.get("max_events_per_month", 12)

    if proto.expected_hold_days < min_hold and status == "eligible_for_research":
        reasons.append(f"Hold {proto.expected_hold_days}d < {min_hold}d minimum.")
        status = "rejected_by_turnover"

    if proto.expected_events_per_month > max_events and status == "eligible_for_research":
        reasons.append(f"Events {proto.expected_events_per_month}/mo > {max_events}/mo maximum.")
        status = "rejected_by_turnover"

    if not reasons:
        reasons.append("Passes all preflight checks.")

    return {
        "strategy_id": proto.strategy_id,
        "name_cn": proto.name_cn,
        "family": proto.family,
        "status": status,
        "reasons": reasons,
        "expected_hold_days": proto.expected_hold_days,
        "expected_events_per_month": proto.expected_events_per_month,
        "executed_legs": proto.executed_legs,
        "resembles_rejected": proto.resembles_rejected,
    }


def run_review(
    risk_map_path: Path,
    registry_path: Path,
) -> dict[str, Any]:
    """Run preflight review on all prototypes."""

    risk_map = load_json(risk_map_path) or {}
    registry = load_json(registry_path) or {}

    # Extract rejected and invalid IDs
    rejected_ids: set[str] = set()
    invalid_ids: set[str] = set()
    for record in registry.get("records", []):
        rid = record.get("research_id", "")
        if record.get("status") == "rejected":
            rejected_ids.add(rid)
        elif record.get("status") == "invalid":
            invalid_ids.add(rid)

    prototypes = get_prototypes()

    reviews: list[dict] = []
    for proto in prototypes:
        review = review_prototype(proto, risk_map, rejected_ids, invalid_ids)
        reviews.append(review)

    # Aggregate counts
    from collections import Counter
    status_counts = Counter(r["status"] for r in reviews)

    # Safety gates: registry top-level values are authoritative; risk_map is fallback.
    trading_perm = risk_map.get("trading_permission", {})
    approved_for_paper = registry.get("approved_for_paper", trading_perm.get("approved_for_paper", []))
    safe_to_enable_trading = registry.get(
        "safe_to_enable_trading",
        trading_perm.get("safe_to_enable_trading", False),
    )

    output = {
        "review_type": "strategy_preflight_review",
        "review_date": "2026-07-13",
        "n_prototypes": len(prototypes),
        "status_counts": dict(status_counts),
        "safety_gates": {
            "approved_for_paper": approved_for_paper,
            "safe_to_enable_trading": safe_to_enable_trading,
        },
        "reviews": reviews,
        "eligible_ids": [r["strategy_id"] for r in reviews if r["status"] == "eligible_for_research"],
        "meta_only_ids": [r["strategy_id"] for r in reviews if r["status"] == "meta_only"],
        "risk_blocked_ids": [r["strategy_id"] for r in reviews if r["status"] == "risk_blocked"],
        "data_blocked_ids": [r["strategy_id"] for r in reviews if r["status"] == "data_blocked"],
        "duplicate_rejected_ids": [r["strategy_id"] for r in reviews if r["status"] == "duplicate_rejected"],
        "rejected_by_cost_ids": [r["strategy_id"] for r in reviews if r["status"] == "rejected_by_cost"],
        "rejected_by_turnover_ids": [r["strategy_id"] for r in reviews if r["status"] == "rejected_by_turnover"],
        "frozen_ids": [r["strategy_id"] for r in reviews if r["status"] == "frozen"],
    }

    return output


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Strategy preflight review.")
    p.add_argument("--risk-map", type=Path, default=Path("reports/research_risk_map.json"))
    p.add_argument("--registry", type=Path, default=Path("reports/research_approval_registry.json"))
    p.add_argument("--out", type=Path, default=Path("reports/strategy_preflight_review.json"))
    args = p.parse_args(argv)

    output = run_review(args.risk_map, args.registry)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")

    print(f"\n{'='*60}")
    print(f"Prototypes: {output['n_prototypes']}")
    for status, ids in [
        ("eligible_for_research", output["eligible_ids"]),
        ("meta_only", output["meta_only_ids"]),
        ("risk_blocked", output["risk_blocked_ids"]),
        ("data_blocked", output["data_blocked_ids"]),
        ("duplicate_rejected", output["duplicate_rejected_ids"]),
        ("rejected_by_cost", output["rejected_by_cost_ids"]),
        ("rejected_by_turnover", output["rejected_by_turnover_ids"]),
        ("frozen", output["frozen_ids"]),
    ]:
        if ids:
            print(f"  {status}: {len(ids)} — {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
