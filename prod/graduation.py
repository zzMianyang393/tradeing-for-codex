"""Local paper graduation evaluator (Stage 2).

Machine-checkable pass/fail for *local paper only*.
Does NOT open OKX demo or live. Even a pass keeps:
- live_allowed = False
- places_exchange_orders = False
- demo/live require separate later-stage promotion after demo effect

Thresholds follow operator roadmap: sufficient closed trades OR completed cycles,
no halt/accident, registry paper_prep when required.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from prod.policy import (
    default_pipeline_places_exchange_orders,
    validate_production_bound_universe,
)


# Frozen Stage-2 local graduation gates (OR on activity metrics).
DEFAULT_MIN_CLOSED_TRADES = 20
DEFAULT_MIN_COMPLETED_CYCLES = 30


@dataclass(frozen=True)
class GraduationThresholds:
    minimum_closed_trades: int = DEFAULT_MIN_CLOSED_TRADES
    minimum_completed_cycles: int = DEFAULT_MIN_COMPLETED_CYCLES
    require_not_halted: bool = True
    require_no_exchange_orders: bool = True
    require_live_disallowed: bool = True
    require_paper_prep_status: bool = True


@dataclass(frozen=True)
class GraduationResult:
    """Explicit graduation decision for local paper."""

    decision: str  # graduated_local | not_yet | blocked
    graduated_local: bool
    live_allowed: bool
    places_exchange_orders: bool
    demo_live_graduation_eligible: bool
    ready_for_demo_stage_consideration: bool
    track_class: str
    reasons: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    as_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _closed_trade_count(state: dict[str, Any]) -> int:
    trades = state.get("closed_trades")
    if isinstance(trades, list):
        return len(trades)
    return int(state.get("closed_trade_count") or 0)


def _completed_cycle_count(state: dict[str, Any], cycle: dict[str, Any] | None = None) -> int:
    if state.get("completed_cycle_count") is not None:
        return int(state["completed_cycle_count"])
    if cycle and cycle.get("completed_cycle_count") is not None:
        return int(cycle["completed_cycle_count"])
    # Fallback: one cycle if last_cycle_at present
    if state.get("last_cycle_at"):
        return 1
    return 0


def evaluate_local_paper_graduation(
    state: dict[str, Any],
    *,
    registry_entry: dict[str, Any] | None = None,
    symbols: Iterable[str] | None = None,
    cycle_report: dict[str, Any] | None = None,
    thresholds: GraduationThresholds | None = None,
) -> GraduationResult:
    """Evaluate local paper graduation from a paper-state snapshot.

    Pure function: no I/O, no exchange calls.
    """
    thr = thresholds or GraduationThresholds()
    blockers: list[str] = []
    reasons: list[str] = []

    halt_reason = state.get("halt_reason")
    live_allowed = bool(state.get("live_allowed", False))
    places = state.get("places_exchange_orders")
    if places is None and cycle_report is not None:
        places = cycle_report.get("places_exchange_orders")
    if places is None:
        places = default_pipeline_places_exchange_orders()
    places = bool(places)
    exchange_submitted = int(
        state.get("exchange_orders_submitted")
        or (cycle_report or {}).get("exchange_orders_submitted")
        or 0
    )

    closed_n = _closed_trade_count(state)
    cycles_n = _completed_cycle_count(state, cycle_report)

    # Universe / track class
    sym_list: list[str]
    if symbols is not None:
        sym_list = list(symbols)
    elif state.get("symbols"):
        sym_list = list(state["symbols"])
    elif cycle_report and cycle_report.get("universe_validation", {}).get("symbols"):
        sym_list = list(cycle_report["universe_validation"]["symbols"])
    else:
        sym_list = []

    if sym_list:
        universe = validate_production_bound_universe(sym_list)
        track_class = universe.track_class
        demo_live_eligible_universe = universe.demo_live_graduation_eligible
    else:
        track_class = str(
            state.get("track_class")
            or (cycle_report or {}).get("track_class")
            or "unknown"
        )
        demo_live_eligible_universe = bool(
            state.get("demo_live_graduation_eligible")
            or (cycle_report or {}).get("demo_live_graduation_eligible")
        )

    if thr.require_not_halted and halt_reason:
        blockers.append(f"halted:{halt_reason}")

    if thr.require_live_disallowed and live_allowed:
        blockers.append("live_allowed_true_forbids_local_graduation_path")

    if thr.require_no_exchange_orders and (places or exchange_submitted > 0):
        blockers.append("exchange_orders_present_or_enabled")

    registry_status = None
    if registry_entry is not None:
        registry_status = registry_entry.get("status")
        if thr.require_paper_prep_status and registry_status not in {
            "paper_prep",
            "graduated_local",
        }:
            blockers.append(f"registry_status_not_paper_prep:{registry_status}")
        if registry_entry.get("live_allowed"):
            blockers.append("registry_live_allowed_true")

    activity_ok = (
        closed_n >= thr.minimum_closed_trades
        or cycles_n >= thr.minimum_completed_cycles
    )
    if not activity_ok:
        reasons.append(
            "insufficient_paper_history"
            f"(closed_trades={closed_n}<{thr.minimum_closed_trades} "
            f"and completed_cycles={cycles_n}<{thr.minimum_completed_cycles})"
        )

    metrics = {
        "closed_trade_count": closed_n,
        "completed_cycle_count": cycles_n,
        "halt_reason": halt_reason,
        "live_allowed_input": live_allowed,
        "places_exchange_orders_input": places,
        "exchange_orders_submitted": exchange_submitted,
        "registry_status": registry_status,
        "track_class": track_class,
        "activity_threshold_met": activity_ok,
    }
    thr_dict = {
        "minimum_closed_trades": thr.minimum_closed_trades,
        "minimum_completed_cycles": thr.minimum_completed_cycles,
        "require_not_halted": thr.require_not_halted,
        "require_no_exchange_orders": thr.require_no_exchange_orders,
        "require_live_disallowed": thr.require_live_disallowed,
        "require_paper_prep_status": thr.require_paper_prep_status,
    }

    # Hard invariants on output regardless of pass
    out_live = False
    out_places = False

    if blockers:
        decision = "blocked"
        graduated = False
        reasons_out = tuple(reasons)
    elif not activity_ok:
        decision = "not_yet"
        graduated = False
        reasons_out = tuple(reasons)
    else:
        decision = "graduated_local"
        graduated = True
        reasons_out = ("local_paper_activity_and_safety_gates_passed",)

    # Demo/live consideration only if local graduated AND production-bound universe.
    # Still does NOT enable live or exchange.
    ready_demo = bool(graduated and demo_live_eligible_universe)
    if graduated and not demo_live_eligible_universe:
        reasons_out = reasons_out + (
            "local_graduated_but_universe_not_demo_live_eligible",
        )

    return GraduationResult(
        decision=decision,
        graduated_local=graduated,
        live_allowed=out_live,
        places_exchange_orders=out_places,
        demo_live_graduation_eligible=bool(demo_live_eligible_universe),
        ready_for_demo_stage_consideration=ready_demo,
        track_class=track_class,
        reasons=reasons_out,
        blockers=tuple(blockers),
        metrics=metrics,
        thresholds=thr_dict,
        as_of=_utc_now(),
    )


def evaluate_from_runtime_files(
    *,
    state: dict[str, Any] | None,
    cycle_report: dict[str, Any] | None = None,
    registry_entry: dict[str, Any] | None = None,
    symbols: Iterable[str] | None = None,
    thresholds: GraduationThresholds | None = None,
) -> GraduationResult:
    """Convenience wrapper when state may be missing."""
    if not state:
        return GraduationResult(
            decision="not_yet",
            graduated_local=False,
            live_allowed=False,
            places_exchange_orders=False,
            demo_live_graduation_eligible=False,
            ready_for_demo_stage_consideration=False,
            track_class="unknown",
            reasons=("paper_state_missing",),
            blockers=(),
            metrics={"closed_trade_count": 0, "completed_cycle_count": 0},
            thresholds=asdict(thresholds or GraduationThresholds()),
            as_of=_utc_now(),
        )
    return evaluate_local_paper_graduation(
        state,
        registry_entry=registry_entry,
        symbols=symbols,
        cycle_report=cycle_report,
        thresholds=thresholds,
    )
