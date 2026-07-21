"""Pre-registered second-stage promotion rules for the frozen event-trend v2.

This module is deliberately independent from the active prospective observer.  The
current 90-day gate can only promote the strategy to paper trading.  A later live
pilot must use new, non-overlapping observations and pass the stronger rules here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
from typing import Any, Iterable

from ten_u_event_trend_contract_v1 import _jsonable
from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig


HOUR_MS = 60 * 60 * 1000


@dataclass(frozen=True)
class FinalPromotionGateV2:
    version: str = "v1.2.0"
    observation_mode: str = "paper_only_forward_observation"
    minimum_calendar_days: int = 180
    minimum_completed_signal_outcomes: int = 20
    event_cluster_horizon_hours: int = 48
    minimum_independent_event_clusters: int = 8
    minimum_executed_trades: int = 12
    minimum_wins: int = 4
    minimum_distinct_traded_symbols: int = 2
    minimum_profit_factor: Decimal = Decimal("1.35")
    minimum_profit_factor_excluding_top_winner: Decimal = Decimal("1.00")
    minimum_ending_equity: Decimal = Decimal("10")
    maximum_drawdown_fraction: Decimal = Decimal("0.60")
    minimum_peak_profit_retention: Decimal = Decimal("0.60")
    maximum_stopped_then_recovered_fraction: Decimal = Decimal("0.35")
    minimum_median_winner_capture: Decimal = Decimal("0.40")
    maximum_top_winner_gross_profit_contribution: Decimal = Decimal("0.60")
    stress_slippage_each_side: Decimal = Decimal("0.0010")
    minimum_stress_profit_factor: Decimal = Decimal("1.00")
    minimum_stress_ending_equity: Decimal = Decimal("10")
    result_policy: str = "first_mature_stage_two_evaluation_is_binding"
    overlap_policy: str = "exclude_every_signal_seen_by_stage_one"
    parameter_policy: str = "no_parameter_change_between_stages"

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def build_final_promotion_preregistration() -> dict[str, Any]:
    """Return rules that can be committed before any stage-one outcome is read."""
    config = PersistentEventTrendConfig()
    gate = FinalPromotionGateV2()
    return {
        "registration_version": "v1.2.0",
        "formal_status": "pre_registered_before_stage_one_outcomes",
        "strategy_id": config.strategy_id,
        "config_fingerprint": config.fingerprint(),
        "stage_one_role": "screen_for_paper_only",
        "stage_two_role": "screen_for_capped_live_pilot_only",
        "stage_two_start": "first_completed_hour_after_stage_one_binding_decision",
        "stage_one_records_reusable": False,
        "amendment_basis": "event_clusters_and_execution_stress_added_while_stage_one_ledger_empty",
        "gate": gate.to_dict(),
        "gate_fingerprint": gate.fingerprint(),
        "outcomes_accessed_at_registration": False,
    }


def robust_profit_metrics(trades: Iterable[dict[str, Any]]) -> dict[str, float]:
    """Measure dependence on the largest winning trade without changing sizing."""
    pnls = [float(trade["net_pnl"]) for trade in trades]
    winners = [value for value in pnls if value > 0]
    losses = [-value for value in pnls if value < 0]
    gross_profit = sum(winners)
    gross_loss = sum(losses)
    top_winner = max(winners, default=0.0)
    residual_profit = gross_profit - top_winner
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
        excluding_top = residual_profit / gross_loss
    else:
        profit_factor = float("inf") if gross_profit > 0 else 0.0
        excluding_top = float("inf") if residual_profit > 0 else 0.0
    return {
        "top_winner_gross_profit_contribution": (
            top_winner / gross_profit if gross_profit > 0 else 0.0
        ),
        "profit_factor": profit_factor,
        "profit_factor_excluding_top_winner": excluding_top,
    }


def count_independent_event_clusters(
    entry_timestamps_ms: Iterable[int], horizon_hours: int = 48
) -> int:
    """Count connected components of overlapping forward outcome intervals."""
    timestamps = sorted({int(value) for value in entry_timestamps_ms})
    if not timestamps:
        return 0
    horizon_ms = horizon_hours * HOUR_MS
    clusters = 1
    cluster_end = timestamps[0] + horizon_ms
    for timestamp in timestamps[1:]:
        # Intervals are [entry, entry + horizon); equality starts a new event.
        if timestamp >= cluster_end:
            clusters += 1
            cluster_end = timestamp + horizon_ms
        else:
            cluster_end = max(cluster_end, timestamp + horizon_ms)
    return clusters


def evaluate_final_promotion(
    replay: dict[str, Any], *, completed_signal_outcomes: int, calendar_days: int,
    completed_signal_entry_ts: Iterable[int], stress_replay: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Evaluate a mature, stage-two-only replay; never promotes directly to full live."""
    gate = FinalPromotionGateV2()
    robust = robust_profit_metrics(replay.get("trades_detail", ()))
    stress_robust = (
        robust_profit_metrics(stress_replay.get("trades_detail", ()))
        if stress_replay is not None
        else {
            "profit_factor": 0.0,
            "profit_factor_excluding_top_winner": 0.0,
            "top_winner_gross_profit_contribution": 0.0,
        }
    )
    if stress_replay is not None:
        if Decimal(str(stress_replay.get("slippage_each_side"))) != gate.stress_slippage_each_side:
            raise ValueError("stress replay does not use the preregistered slippage")
        identity_fields = ("symbol", "direction", "entry_ts")
        base_identities = [
            tuple(trade[field] for field in identity_fields)
            for trade in replay.get("trades_detail", ())
        ]
        stress_identities = [
            tuple(trade[field] for field in identity_fields)
            for trade in stress_replay.get("trades_detail", ())
        ]
        if base_identities != stress_identities:
            raise ValueError("stress replay trade identities differ from the base replay")
    signal_entries = list(completed_signal_entry_ts)
    if len(signal_entries) != completed_signal_outcomes:
        raise ValueError("one entry timestamp is required for every completed signal outcome")
    event_clusters = count_independent_event_clusters(
        signal_entries, gate.event_cluster_horizon_hours
    )
    traded_symbols = sum(
        int(count) > 0 for count in replay.get("trades_by_symbol", {}).values()
    )
    checks = (
        (calendar_days < gate.minimum_calendar_days, "calendar_days_below_minimum"),
        (
            completed_signal_outcomes < gate.minimum_completed_signal_outcomes,
            "completed_signal_outcomes_below_minimum",
        ),
        (
            event_clusters < gate.minimum_independent_event_clusters,
            "independent_event_clusters_below_minimum",
        ),
        (replay.get("trades", 0) < gate.minimum_executed_trades, "executed_trades_below_minimum"),
        (replay.get("wins", 0) < gate.minimum_wins, "wins_below_minimum"),
        (traded_symbols < gate.minimum_distinct_traded_symbols, "distinct_symbols_below_minimum"),
        (robust["profit_factor"] < float(gate.minimum_profit_factor), "profit_factor_below_minimum"),
        (
            robust["profit_factor_excluding_top_winner"]
            < float(gate.minimum_profit_factor_excluding_top_winner),
            "profit_factor_excluding_top_winner_below_minimum",
        ),
        (replay.get("ending_equity", 0) < float(gate.minimum_ending_equity), "ending_equity_below_minimum"),
        (
            replay.get("max_drawdown_fraction", 1) > float(gate.maximum_drawdown_fraction),
            "drawdown_above_maximum",
        ),
        (
            replay.get("peak_profit_retention", 0) < float(gate.minimum_peak_profit_retention),
            "peak_profit_retention_below_minimum",
        ),
        (
            replay.get("stopped_then_recovered_fraction", 1)
            > float(gate.maximum_stopped_then_recovered_fraction),
            "stopped_then_recovered_above_maximum",
        ),
        (
            replay.get("median_winner_capture", 0) < float(gate.minimum_median_winner_capture),
            "median_winner_capture_below_minimum",
        ),
        (
            robust["top_winner_gross_profit_contribution"]
            > float(gate.maximum_top_winner_gross_profit_contribution),
            "top_winner_contribution_above_maximum",
        ),
        (stress_replay is None, "execution_stress_replay_missing"),
        (
            stress_robust["profit_factor"] < float(gate.minimum_stress_profit_factor),
            "stress_profit_factor_below_minimum",
        ),
        (
            stress_replay is None
            or stress_replay.get("ending_equity", 0) < float(gate.minimum_stress_ending_equity),
            "stress_ending_equity_below_minimum",
        ),
    )
    reasons = [reason for failed, reason in checks if failed]
    passed = not reasons
    return {
        "formal_status": "stage_two_pass" if passed else "stage_two_not_passed",
        "decision": "eligible_for_capped_live_pilot" if passed else "do_not_enable_live_capital",
        "gate_fingerprint": gate.fingerprint(),
        "completed_signal_outcomes": completed_signal_outcomes,
        "independent_event_clusters": event_clusters,
        "calendar_days": calendar_days,
        "distinct_traded_symbols": traded_symbols,
        **robust,
        "stress_slippage_each_side": float(gate.stress_slippage_each_side),
        "stress_profit_factor": stress_robust["profit_factor"],
        "stress_ending_equity": stress_replay.get("ending_equity") if stress_replay else None,
        "reasons": reasons,
    }


if __name__ == "__main__":
    print(json.dumps(build_final_promotion_preregistration(), indent=2))
