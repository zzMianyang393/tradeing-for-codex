"""Gate future research toward low-turnover strategies."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


MIN_HOLD_DAYS = 3.0
MAX_EVENTS_PER_MONTH = 12
MAX_TURNOVER_COST_PER_MONTH = 0.10
SINGLE_MARKET_ROUND_TRIP_COST = 0.0016
FOUR_LEG_ROUND_TRIP_COST = 0.0032


@dataclass(frozen=True)
class ResearchGateInput:
    name: str
    expected_hold_days: float
    expected_events_per_month: int
    executed_legs: int


@dataclass(frozen=True)
class ResearchGateResult:
    name: str
    passed: bool
    expected_hold_days: float
    expected_events_per_month: int
    executed_legs: int
    round_trip_cost: float
    projected_monthly_cost: float
    failures: tuple[str, ...]


def round_trip_cost_for_legs(executed_legs: int) -> float:
    if executed_legs == 2:
        return SINGLE_MARKET_ROUND_TRIP_COST
    if executed_legs == 4:
        return FOUR_LEG_ROUND_TRIP_COST
    if executed_legs <= 0:
        raise ValueError("executed_legs must be positive")
    return round(executed_legs * 0.0008, 10)


def evaluate_low_turnover_candidate(candidate: ResearchGateInput) -> ResearchGateResult:
    if candidate.expected_events_per_month < 0:
        raise ValueError("expected_events_per_month must be non-negative")
    cost = round_trip_cost_for_legs(candidate.executed_legs)
    projected_monthly_cost = round(cost * candidate.expected_events_per_month, 10)
    failures: list[str] = []
    if candidate.expected_hold_days < MIN_HOLD_DAYS:
        failures.append("hold_period_too_short")
    if candidate.expected_events_per_month > MAX_EVENTS_PER_MONTH:
        failures.append("too_many_events_per_month")
    if projected_monthly_cost > MAX_TURNOVER_COST_PER_MONTH:
        failures.append("turnover_cost_too_high")
    return ResearchGateResult(
        name=candidate.name,
        passed=not failures,
        expected_hold_days=candidate.expected_hold_days,
        expected_events_per_month=candidate.expected_events_per_month,
        executed_legs=candidate.executed_legs,
        round_trip_cost=cost,
        projected_monthly_cost=projected_monthly_cost,
        failures=tuple(failures),
    )


def build_low_turnover_policy_report() -> dict[str, Any]:
    examples = [
        ResearchGateInput("daily_breakout_many_events", 0.5, 90, 2),
        ResearchGateInput("weekly_trend_following_candidate", 7.0, 4, 2),
        ResearchGateInput("market_neutral_carry_candidate", 14.0, 2, 4),
        ResearchGateInput("calendar_spread_intraday_reversion", 0.02, 400, 4),
    ]
    results = [evaluate_low_turnover_candidate(item) for item in examples]
    return {
        "audit_id": "low_turnover_research_gate_2026-07-12",
        "purpose": "Prevent future research from re-entering high-turnover small-edge parameter searches.",
        "thresholds": {
            "min_hold_days": MIN_HOLD_DAYS,
            "max_events_per_month": MAX_EVENTS_PER_MONTH,
            "max_turnover_cost_per_month": MAX_TURNOVER_COST_PER_MONTH,
        },
        "examples": [asdict(item) for item in results],
        "hard_rules": [
            "New strategy research must declare expected hold period, monthly events, and executed legs before coding.",
            "Expected hold period below 3 days is rejected unless the research is explicitly meta-only.",
            "Expected events above 12 per month are rejected unless gross edge is proven before parameter search.",
            "Projected monthly execution cost above 10% is rejected before event audit.",
        ],
        "decision": "meta_only_not_strategy",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write low-turnover research gate report.")
    parser.add_argument("--out", type=Path, default=Path("reports/low_turnover_research_gate.json"))
    args = parser.parse_args(argv)
    report = build_low_turnover_policy_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
