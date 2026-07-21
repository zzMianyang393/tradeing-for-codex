"""Execution cost floor audit for future OKX strategy research."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PER_EXECUTED_LEG_COST = 0.0008
SINGLE_MARKET_ROUND_TRIP_LEGS = 2
TWO_MARKET_ROUND_TRIP_LEGS = 4


@dataclass(frozen=True)
class CostScenario:
    name: str
    executed_legs: int
    round_trip_cost: float
    min_gross_for_zero_net: float
    min_gross_for_10bp_net: float
    min_gross_for_25bp_net: float
    min_gross_for_50bp_net: float


def cost_for_legs(executed_legs: int, per_leg_cost: float = PER_EXECUTED_LEG_COST) -> float:
    if executed_legs <= 0:
        raise ValueError("executed_legs must be positive")
    if per_leg_cost < 0:
        raise ValueError("per_leg_cost must be non-negative")
    return executed_legs * per_leg_cost


def scenario(name: str, executed_legs: int) -> CostScenario:
    cost = cost_for_legs(executed_legs)
    return CostScenario(
        name=name,
        executed_legs=executed_legs,
        round_trip_cost=round(cost, 10),
        min_gross_for_zero_net=round(cost, 10),
        min_gross_for_10bp_net=round(cost + 0.0010, 10),
        min_gross_for_25bp_net=round(cost + 0.0025, 10),
        min_gross_for_50bp_net=round(cost + 0.0050, 10),
    )


def daily_cost_drag(round_trip_cost: float, trades_per_day: float) -> float:
    if round_trip_cost < 0:
        raise ValueError("round_trip_cost must be non-negative")
    if trades_per_day < 0:
        raise ValueError("trades_per_day must be non-negative")
    return round_trip_cost * trades_per_day


def build_cost_floor_audit() -> dict[str, Any]:
    scenarios = [
        scenario("single_market_directional_round_trip", SINGLE_MARKET_ROUND_TRIP_LEGS),
        scenario("two_market_neutral_round_trip", TWO_MARKET_ROUND_TRIP_LEGS),
        scenario("calendar_spread_round_trip", TWO_MARKET_ROUND_TRIP_LEGS),
    ]
    turnover_grid: dict[str, dict[str, float]] = {}
    for item in scenarios:
        turnover_grid[item.name] = {
            "1_trade_per_day": daily_cost_drag(item.round_trip_cost, 1),
            "3_trades_per_day": daily_cost_drag(item.round_trip_cost, 3),
            "10_trades_per_day": daily_cost_drag(item.round_trip_cost, 10),
            "100_trades_per_month": item.round_trip_cost * 100,
            "1000_trades_per_month": item.round_trip_cost * 1000,
        }
    return {
        "audit_id": "execution_cost_floor_audit_2026-07-12",
        "purpose": "Set gross-return floors before future strategy research.",
        "per_executed_leg_cost": PER_EXECUTED_LEG_COST,
        "scenarios": [asdict(item) for item in scenarios],
        "turnover_cost_drag": turnover_grid,
        "hard_rules": [
            "Single-market directional round trips must clear at least 0.16% gross before any edge exists.",
            "Two-market neutral or calendar-spread round trips must clear at least 0.32% gross before any edge exists.",
            "Strategies producing many sub-0.32% events should be rejected before parameter search.",
            "Future research should prefer lower turnover unless it can prove per-event gross edge materially exceeds the relevant floor.",
        ],
        "decision": "meta_only_not_strategy",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write execution cost floor audit.")
    parser.add_argument("--out", type=Path, default=Path("reports/execution_cost_floor_audit.json"))
    args = parser.parse_args(argv)
    report = build_cost_floor_audit()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
