"""Pre-registered mean-reversion audit for OKX futures calendar spreads."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from okx_futures_calendar_spread_pipeline import FOUR_LEG_ROUND_TRIP_COST, format_utc, parse_utc_ms


ONE_MINUTE_MS = 60 * 1000
ROLLING_LOOKBACK_ROWS = 7 * 24 * 60
ENTRY_Z = 2.0
EXIT_Z = 0.25
MAX_HOLD_ROWS = 72 * 60
ROUND_TRIP_COST = FOUR_LEG_ROUND_TRIP_COST
FORMATION_START = parse_utc_ms("2025-06-01 00:00:00")
FORMATION_END = parse_utc_ms("2025-12-31 23:59:59")
OOS_START = parse_utc_ms("2026-01-01 00:00:00")
OOS_END = parse_utc_ms("2026-06-23 07:59:00")


@dataclass(frozen=True)
class SpreadPoint:
    ts: int
    future_inst_id: str
    spread_pct: float


@dataclass(frozen=True)
class Trade:
    entry_ts: int
    exit_ts: int
    side: str
    future_inst_id: str
    entry_spread_pct: float
    exit_spread_pct: float
    entry_z: float
    exit_z: float
    hold_minutes: int
    gross_return: float
    net_return: float
    exit_reason: str


class RollingZScore:
    def __init__(self, maxlen: int):
        self.values: deque[float] = deque(maxlen=maxlen)
        self.total = 0.0
        self.total_sq = 0.0
        self.maxlen = maxlen

    def append(self, value: float) -> None:
        if len(self.values) == self.maxlen:
            old = self.values[0]
            self.total -= old
            self.total_sq -= old * old
        self.values.append(value)
        self.total += value
        self.total_sq += value * value

    def zscore(self, value: float) -> float | None:
        count = len(self.values)
        if count < self.maxlen:
            return None
        mean = self.total / count
        variance = max(0.0, self.total_sq / count - mean * mean)
        std = math.sqrt(variance)
        if std <= 0:
            return None
        return (value - mean) / std


def read_spread_points(path: Path) -> list[SpreadPoint]:
    points: list[SpreadPoint] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                points.append(
                    SpreadPoint(
                        ts=int(row["timestamp_ms"]),
                        future_inst_id=row["future_inst_id"],
                        spread_pct=float(row["spread_pct"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(points, key=lambda point: point.ts)


def _gross_return(side: str, entry_spread: float, exit_spread: float) -> float:
    if side == "short_spread":
        return entry_spread - exit_spread
    if side == "long_spread":
        return exit_spread - entry_spread
    raise ValueError(f"unknown side: {side}")


def generate_trades(points: list[SpreadPoint]) -> list[Trade]:
    rolling = RollingZScore(ROLLING_LOOKBACK_ROWS)
    trades: list[Trade] = []
    position: dict[str, Any] | None = None
    previous_point: SpreadPoint | None = None
    previous_z: float | None = None

    for point in points:
        z = rolling.zscore(point.spread_pct)
        if position is not None and previous_point is not None:
            exit_point = point
            exit_z = z if z is not None else 0.0
            reason: str | None = None
            if point.future_inst_id != position["future_inst_id"]:
                exit_point = previous_point
                exit_z = previous_z if previous_z is not None else 0.0
                reason = "rollover_guard"
            elif position["side"] == "short_spread" and z is not None and z <= EXIT_Z:
                reason = "mean_reversion"
            elif position["side"] == "long_spread" and z is not None and z >= -EXIT_Z:
                reason = "mean_reversion"
            elif (point.ts - position["entry_ts"]) // ONE_MINUTE_MS >= MAX_HOLD_ROWS:
                reason = "max_hold"
            if reason is not None:
                gross = _gross_return(position["side"], position["entry_spread_pct"], exit_point.spread_pct)
                trades.append(
                    Trade(
                        entry_ts=position["entry_ts"],
                        exit_ts=exit_point.ts,
                        side=position["side"],
                        future_inst_id=position["future_inst_id"],
                        entry_spread_pct=position["entry_spread_pct"],
                        exit_spread_pct=exit_point.spread_pct,
                        entry_z=position["entry_z"],
                        exit_z=exit_z,
                        hold_minutes=max(0, (exit_point.ts - position["entry_ts"]) // ONE_MINUTE_MS),
                        gross_return=gross,
                        net_return=gross - ROUND_TRIP_COST,
                        exit_reason=reason,
                    )
                )
                position = None

        if position is None and z is not None:
            if z >= ENTRY_Z:
                position = {
                    "entry_ts": point.ts,
                    "side": "short_spread",
                    "future_inst_id": point.future_inst_id,
                    "entry_spread_pct": point.spread_pct,
                    "entry_z": z,
                }
            elif z <= -ENTRY_Z:
                position = {
                    "entry_ts": point.ts,
                    "side": "long_spread",
                    "future_inst_id": point.future_inst_id,
                    "entry_spread_pct": point.spread_pct,
                    "entry_z": z,
                }

        rolling.append(point.spread_pct)
        previous_point = point
        previous_z = z

    return trades


def summarize_trades(trades: list[Trade], start_ts: int, end_ts: int) -> dict[str, Any]:
    window_trades = [trade for trade in trades if start_ts <= trade.entry_ts <= end_ts]
    wins = [trade.net_return for trade in window_trades if trade.net_return > 0]
    losses = [trade.net_return for trade in window_trades if trade.net_return <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    month_counts = Counter(datetime.fromtimestamp(trade.entry_ts / 1000, tz=timezone.utc).strftime("%Y-%m") for trade in window_trades)
    return {
        "start_utc": format_utc(start_ts),
        "end_utc": format_utc(end_ts),
        "events": len(window_trades),
        "net_return_sum": sum(trade.net_return for trade in window_trades),
        "net_return_mean": sum(trade.net_return for trade in window_trades) / len(window_trades) if window_trades else 0.0,
        "gross_return_sum": sum(trade.gross_return for trade in window_trades),
        "win_rate": len(wins) / len(window_trades) if window_trades else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else (float("inf") if gross_profit else 0.0),
        "avg_hold_minutes": sum(trade.hold_minutes for trade in window_trades) / len(window_trades) if window_trades else 0.0,
        "top_month_concentration": max(month_counts.values()) / len(window_trades) if window_trades else 0.0,
        "month_counts": dict(sorted(month_counts.items())),
        "exit_reasons": dict(sorted(Counter(trade.exit_reason for trade in window_trades).items())),
    }


def audit_spread_mean_reversion(spread_path: Path) -> dict[str, Any]:
    points = read_spread_points(spread_path)
    trades = generate_trades(points)
    formation = summarize_trades(trades, FORMATION_START, FORMATION_END)
    oos = summarize_trades(trades, OOS_START, OOS_END)
    formation_passed = (
        formation["events"] >= 60
        and formation["net_return_mean"] > 0
        and formation["win_rate"] >= 0.52
        and formation["profit_factor"] >= 1.2
        and formation["top_month_concentration"] <= 0.30
    )
    oos_passed = (
        oos["events"] >= 30
        and oos["net_return_mean"] > 0
        and oos["win_rate"] >= 0.50
        and oos["profit_factor"] >= 1.05
    )
    decision = "eligible_for_review" if formation_passed and oos_passed else "rejected"
    return {
        "strategy_id": "okx_futures_calendar_spread_mean_reversion_v1",
        "spread_path": str(spread_path),
        "rule": {
            "lookback_rows": ROLLING_LOOKBACK_ROWS,
            "entry_z": ENTRY_Z,
            "exit_z": EXIT_Z,
            "max_hold_rows": MAX_HOLD_ROWS,
            "round_trip_cost": ROUND_TRIP_COST,
            "rollover_policy": "no_position_across_future_inst_id_change",
        },
        "total_trades": len(trades),
        "formation": formation,
        "oos": oos,
        "formation_passed": formation_passed,
        "oos_passed": oos_passed,
        "decision": decision,
        "sample_trades": [
            {
                "entry_utc": format_utc(trade.entry_ts),
                "exit_utc": format_utc(trade.exit_ts),
                "side": trade.side,
                "future_inst_id": trade.future_inst_id,
                "entry_spread_pct": trade.entry_spread_pct,
                "exit_spread_pct": trade.exit_spread_pct,
                "entry_z": trade.entry_z,
                "exit_z": trade.exit_z,
                "hold_minutes": trade.hold_minutes,
                "gross_return": trade.gross_return,
                "net_return": trade.net_return,
                "exit_reason": trade.exit_reason,
            }
            for trade in trades[:20]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit pre-registered OKX calendar-spread mean reversion.")
    parser.add_argument("--spread", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/okx_futures_calendar_spread_mean_reversion_audit.json"))
    args = parser.parse_args(argv)
    report = audit_spread_mean_reversion(args.spread)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
