"""Feature pool preflight review: group features by allowed role before coding.

Reads: reports/strategy_feature_pool.json
Outputs: grouped features with blocking reasons.

This is a PLANNING tool.  It does NOT create strategies or connect to runner.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


HARD_BLOCK_IDS = {
    "pairs_walk_forward",
    "spot_perp_basis",
    "positive_funding_carry",
    "btc_alt_lead_lag",
    "okx_futures_calendar_spread",
    "utc_session_breakout_family",
    "regime_component_shared_capital_combo",
}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def review_feature_pool(pool: dict) -> dict[str, Any]:
    """Group features by allowed role."""

    features = pool.get("features", [])

    directional: list[dict] = []
    context: list[dict] = []
    risk_filter: list[dict] = []
    blocked: list[dict] = []

    for f in features:
        role = f.get("feature_role", "blocked")
        fid = f.get("feature_id", "")
        rid = f.get("source_research_id", "")
        status = f.get("source_status", "")
        tags = f.get("tags", [])
        block_reasons = f.get("block_reasons", [])

        entry = {
            "feature_id": fid,
            "source_research_id": rid,
            "source_status": status,
            "tags": tags,
            "requires_concentration_penalty": "concentration_risk" in tags,
        }

        if status in ("invalid", "data_blocked", "risk_blocked") or rid in HARD_BLOCK_IDS:
            reasons = list(block_reasons)
            if rid in HARD_BLOCK_IDS and not reasons:
                reasons.append("Hard blocked from combo directional reuse.")
            entry["block_reasons"] = reasons
            blocked.append(entry)
        elif role == "blocked":
            entry["block_reasons"] = block_reasons
            blocked.append(entry)
        elif role == "directional_weak_signal":
            # Check if OOS is empty (no_oos_entries tag) -> demote to context
            if "no_oos_entries" in tags:
                entry["demoted_to_context"] = True
                entry["demote_reason"] = "No OOS entries; cannot be directional signal."
                context.append(entry)
            else:
                directional.append(entry)
        elif role == "context_label":
            context.append(entry)
        elif role == "risk_filter_candidate":
            risk_filter.append(entry)
        else:
            entry["block_reasons"] = [f"Unknown role: {role}"]
            blocked.append(entry)

    return {
        "review_type": "feature_pool_preflight_review",
        "review_date": "2026-07-13",
        "n_features": len(features),
        "groups": {
            "directional_feature_candidates": directional,
            "context_label_candidates": context,
            "risk_filter_candidates": risk_filter,
            "blocked_features": blocked,
        },
        "group_counts": {
            "directional": len(directional),
            "context": len(context),
            "risk_filter": len(risk_filter),
            "blocked": len(blocked),
        },
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Feature pool preflight review.")
    p.add_argument("--pool", type=Path, default=Path("reports/strategy_feature_pool.json"))
    p.add_argument("--out", type=Path, default=Path("reports/feature_pool_preflight_review.json"))
    args = p.parse_args(argv)

    pool = load_json(args.pool)
    if not pool:
        print("ERROR: Cannot load feature pool")
        return 1

    review = review_feature_pool(pool)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")

    counts = review["group_counts"]
    print(f"\nDirectional: {counts['directional']}")
    print(f"Context:     {counts['context']}")
    print(f"Risk filter: {counts['risk_filter']}")
    print(f"Blocked:     {counts['blocked']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
