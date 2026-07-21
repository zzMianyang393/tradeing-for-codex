"""Build a meta-only research risk map.

The risk map aggregates existing meta audits into one machine-readable report.
It is a research planning artifact only: it does not create trading signals,
filters, or runner hooks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_cost_constraints(cost_report: dict[str, Any]) -> dict[str, Any]:
    scenarios = {item["name"]: item for item in cost_report.get("scenarios", [])}
    return {
        "single_market_round_trip_cost": scenarios.get("single_market_directional_round_trip", {}).get("round_trip_cost"),
        "two_market_round_trip_cost": scenarios.get("two_market_neutral_round_trip", {}).get("round_trip_cost"),
        "calendar_spread_round_trip_cost": scenarios.get("calendar_spread_round_trip", {}).get("round_trip_cost"),
        "rules": cost_report.get("hard_rules", []),
    }


def build_turnover_constraints(turnover_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "thresholds": turnover_report.get("thresholds", {}),
        "rules": turnover_report.get("hard_rules", []),
    }


def build_filter_constraints(filter_report: dict[str, Any]) -> dict[str, Any]:
    candidates = filter_report.get("filter_candidates", [])
    return {
        "evidence_level": "weak_observation_only",
        "events_analysed": filter_report.get("n_events_analysed", 0),
        "reports_processed": filter_report.get("n_reports_processed", 0),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "warning": "Do not convert these candidates into hard filters without larger rejected-event coverage.",
    }


def build_oi_state(oi_report: dict[str, Any]) -> dict[str, Any]:
    summary = oi_report.get("summary", {})
    formation = summary.get("formation", {})
    oos = summary.get("oos", {})
    return {
        "state_id": "high_oivr_leverage_state",
        "allowed_use": "context_label_only",
        "not_allowed": ["entry_signal", "hard_no_trade_filter", "paper_trading_gate"],
        "formation_events": formation.get("events", 0),
        "formation_abs_3d_mean_pct": formation.get("abs_fwd_3d", {}).get("mean_pct", 0.0),
        "formation_abs_7d_mean_pct": formation.get("abs_fwd_7d", {}).get("mean_pct", 0.0),
        "oos_events": oos.get("events", 0),
        "oos_abs_3d_mean_pct": oos.get("abs_fwd_3d", {}).get("mean_pct", 0.0),
        "oos_abs_7d_mean_pct": oos.get("abs_fwd_7d", {}).get("mean_pct", 0.0),
        "verdict": oi_report.get("verdict", {}),
    }


def build_registry_snapshot(registry: dict[str, Any]) -> dict[str, Any]:
    return {
        "status_counts": registry.get("status_counts", {}),
        "approved_for_paper": registry.get("approved_for_paper", []),
        "approved_research": registry.get("approved_research", []),
        "safe_to_enable_trading": registry.get("safe_to_enable_trading", False),
    }


def build_risk_map(reports_dir: Path) -> dict[str, Any]:
    cost = load_json(reports_dir / "execution_cost_floor_audit.json")
    turnover = load_json(reports_dir / "low_turnover_research_gate.json")
    no_trade = load_json(reports_dir / "no_trade_filter_research.json")
    oi = load_json(reports_dir / "oi_deleveraging_filter_audit.json")
    registry = load_json(reports_dir / "research_approval_registry.json")
    return {
        "risk_map_id": "research_risk_map_2026-07-13",
        "scope": "meta_only_research_planning_not_strategy",
        "trading_permission": build_registry_snapshot(registry),
        "cost_constraints": build_cost_constraints(cost),
        "turnover_constraints": build_turnover_constraints(turnover),
        "failure_filter_observations": build_filter_constraints(no_trade),
        "risk_state_labels": [build_oi_state(oi)],
        "pre_research_checklist": [
            "Reject strategy proposals that cannot clear the relevant explicit cost floor.",
            "Reject or mark meta-only proposals with expected hold period below 3 days.",
            "Reject or mark meta-only proposals with expected events above 12 per month unless gross edge is proven first.",
            "Treat no-trade filter candidates as weak observations until rejected-event coverage is much broader.",
            "Use OI deleveraging only as a context label, never as an entry signal or hard no-trade rule.",
            "Do not enable paper trading unless registry approved_for_paper is non-empty.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build research risk map.")
    parser.add_argument("--reports", type=Path, default=Path("reports"))
    parser.add_argument("--out", type=Path, default=Path("reports/research_risk_map.json"))
    args = parser.parse_args(argv)
    payload = build_risk_map(args.reports)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
