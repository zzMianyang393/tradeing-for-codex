"""Combo research readiness review.

This is a planning gate for the combo research layer. It reads the feature pool
preflight report and decides whether the project is ready for a combo backtest,
or only ready for feature time-series extraction and diagnostics.

It does not import runner.py, does not create strategies, and never approves
paper trading.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MIN_DIRECTIONAL_FEATURES_FOR_BACKTEST = 3


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def readiness_review(preflight: dict[str, Any]) -> dict[str, Any]:
    groups = preflight.get("groups", {})
    directional = groups.get("directional_feature_candidates", [])
    context = groups.get("context_label_candidates", [])
    risk_filter = groups.get("risk_filter_candidates", [])
    blocked = groups.get("blocked_features", [])
    safety = preflight.get("safety_gates", {})

    reasons: list[str] = []
    warnings: list[str] = []

    if safety.get("approved_for_paper", []) != []:
        reasons.append("approved_for_paper is not empty")
    if safety.get("safe_to_enable_trading", False) is not False:
        reasons.append("safe_to_enable_trading is not false")

    if len(directional) < MIN_DIRECTIONAL_FEATURES_FOR_BACKTEST:
        reasons.append(
            f"directional features {len(directional)} < {MIN_DIRECTIONAL_FEATURES_FOR_BACKTEST} minimum for combo backtest"
        )

    concentrated = [item for item in directional if item.get("requires_concentration_penalty")]
    if directional and len(concentrated) == len(directional):
        reasons.append("all directional candidates require concentration penalty")
    elif concentrated:
        warnings.append(f"{len(concentrated)} directional candidates require concentration penalty")

    if not context:
        warnings.append("no context labels available for regime diagnostics")
    if not risk_filter:
        warnings.append("no risk filters available for veto-only diagnostics")
    if not blocked:
        warnings.append("no blocked features listed; feature pool may be under-filtered")

    ready_for_combo_backtest = not reasons
    return {
        "review_type": "combo_research_readiness_review",
        "review_date": "2026-07-13",
        "ready_for_combo_backtest": ready_for_combo_backtest,
        "allowed_next_step": "combo_backtest" if ready_for_combo_backtest else "feature_timeseries_extraction_only",
        "reason_codes": reasons,
        "warnings": warnings,
        "counts": {
            "directional_feature_candidates": len(directional),
            "context_label_candidates": len(context),
            "risk_filter_candidates": len(risk_filter),
            "blocked_features": len(blocked),
            "directional_with_concentration_penalty": len(concentrated),
        },
        "directional_feature_ids": [item.get("source_research_id") for item in directional],
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
        },
        "methodology_notes": [
            "Readiness review is a research gate, not a strategy approval.",
            "A failed readiness review still allows read-only feature time-series extraction.",
            "No combo backtest should run until the readiness gate passes.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review combo research readiness.")
    parser.add_argument("--preflight", type=Path, default=Path("reports/feature_pool_preflight_review.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/combo_research_readiness_review.json"))
    args = parser.parse_args(argv)

    preflight = load_json(args.preflight)
    if not preflight:
        print("ERROR: Cannot load feature pool preflight report")
        return 1

    report = readiness_review(preflight)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Report written to {args.out}")
    print(f"Ready for combo backtest: {report['ready_for_combo_backtest']}")
    print(f"Allowed next step: {report['allowed_next_step']}")
    for reason in report["reason_codes"]:
        print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
