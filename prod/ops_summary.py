"""Operator-facing local paper ops summary (no exchange).

Pure aggregation for status/dashboard-style JSON. Never places orders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prod.graduation import GraduationResult, evaluate_from_runtime_files
from prod.policy import operator_policy_snapshot


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_sleeve_ops_summary(
    *,
    strategy_id: str,
    track_label: str,
    state: dict[str, Any] | None,
    cycle_report: dict[str, Any] | None,
    registry_entry: dict[str, Any] | None,
    graduation: GraduationResult | None = None,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact health block for one sleeve."""
    if graduation is None:
        graduation = evaluate_from_runtime_files(
            state=state,
            cycle_report=cycle_report,
            registry_entry=registry_entry,
            symbols=(state or {}).get("symbols")
            or (cycle_report or {}).get("universe_validation", {}).get("symbols"),
        )

    equity = None
    peak = None
    halt = None
    cycles = 0
    closed = 0
    open_pos = None
    last_cycle_at = None
    mode = "local_paper"
    places = False
    live = False
    track_class = "unknown"

    if state:
        equity = state.get("equity")
        peak = state.get("peak_equity")
        halt = state.get("halt_reason")
        cycles = int(state.get("completed_cycle_count") or 0)
        closed = len(state.get("closed_trades") or [])
        open_pos = state.get("open_position")
        last_cycle_at = state.get("last_cycle_at")
        mode = state.get("mode") or mode
        places = bool(state.get("places_exchange_orders", False))
        live = bool(state.get("live_allowed", False))
        track_class = str(state.get("track_class") or track_class)
    elif cycle_report:
        equity = cycle_report.get("equity")
        peak = cycle_report.get("peak_equity")
        halt = cycle_report.get("halt_reason")
        cycles = int(cycle_report.get("completed_cycle_count") or 0)
        closed = int(cycle_report.get("closed_trade_count") or 0)
        open_pos = cycle_report.get("open_position")
        places = bool(cycle_report.get("places_exchange_orders", False))
        live = bool(cycle_report.get("live_allowed", False))
        track_class = str(cycle_report.get("track_class") or track_class)

    registry_status = (registry_entry or {}).get("status")
    paper_allowed = registry_status in {"paper_prep", "graduated_local"}

    health = "ok"
    alerts: list[str] = []
    if state is None:
        health = "no_state"
        alerts.append("paper_state_missing")
    if halt:
        health = "halted"
        alerts.append(f"halt:{halt}")
    if not paper_allowed and registry_entry is not None:
        if health == "ok":
            health = "registry_blocked"
        alerts.append(f"registry:{registry_status}")
    if places or live:
        health = "policy_violation"
        alerts.append("exchange_or_live_flag_set")
    if graduation.decision == "blocked" and health == "ok":
        health = "graduation_blocked"
        alerts.extend(list(graduation.blockers))

    drawdown = None
    if equity is not None and peak is not None and float(peak) > 0:
        drawdown = 1.0 - float(equity) / float(peak)

    return {
        "report_type": "sleeve_ops_summary",
        "as_of": _utc_now(),
        "strategy_id": strategy_id,
        "track_label": track_label,
        "health": health,
        "alerts": alerts,
        "mode": mode,
        "track_class": track_class,
        "equity": equity,
        "peak_equity": peak,
        "drawdown_fraction": drawdown,
        "halt_reason": halt,
        "completed_cycle_count": cycles,
        "closed_trade_count": closed,
        "has_open_position": open_pos is not None,
        "last_cycle_at": last_cycle_at,
        "registry_status": registry_status,
        "paper_prep_allowed": paper_allowed,
        "places_exchange_orders": places,
        "live_allowed": live,
        "local_graduation": graduation.to_dict(),
        "preflight_status": (preflight or {}).get("formal_status"),
        "notes": (
            "Local paper ops only. health!=ok never implies exchange/demo/live access."
        ),
    }


def compact_readiness_pointer(package: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach a small pointer to a full majors-readiness package (no recompute)."""
    if not package:
        return None
    primary = package.get("primary") or {}
    replay = primary.get("replay_10u") or {}
    cons = package.get("conservative_compare") or {}
    cons_replay = cons.get("replay_10u") or {}
    return {
        "report_type": "majors_readiness_pointer",
        "as_of": package.get("as_of"),
        "formal_status": package.get("formal_status"),
        "places_exchange_orders": package.get("places_exchange_orders", False),
        "live_allowed": package.get("live_allowed", False),
        "ready_for_demo": package.get("ready_for_demo", False),
        "ready_for_live": package.get("ready_for_live", False),
        "primary_10u_ending_equity": replay.get("ending_equity"),
        "primary_10u_trades": replay.get("trades"),
        "primary_fingerprint": (primary.get("config") or {}).get("config_fingerprint")
        or replay.get("config_fingerprint"),
        "conservative_10u_ending_equity": cons_replay.get("ending_equity"),
        "conservative_10u_trades": cons_replay.get("trades"),
        "local_graduation_decision": (package.get("local_graduation") or {}).get(
            "decision"
        ),
        "admission_notes_head": list(package.get("admission_notes") or [])[:6],
        "source_report_type": package.get("report_type"),
    }


def load_readiness_package_file(path: Path) -> dict[str, Any] | None:
    import json

    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_prod_ops_dashboard(
    *,
    majors_summary: dict[str, Any],
    ten_u_summary: dict[str, Any],
    majors_readiness_pointer: dict[str, Any] | None = None,
    majors_refresh_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = operator_policy_snapshot()
    overall = "ok"
    for block in (majors_summary, ten_u_summary):
        h = block.get("health")
        if h in {"halted", "policy_violation"}:
            overall = "critical"
            break
        if h not in {"ok", "no_state"} and overall == "ok":
            overall = "degraded"
        if h == "no_state" and overall == "ok":
            overall = "partial"

    return {
        "report_type": "prod_ops_dashboard",
        "as_of": _utc_now(),
        "overall_health": overall,
        "operator_policy": policy,
        "default_pipeline_places_exchange_orders": policy[
            "default_pipeline_places_exchange_orders"
        ],
        "sleeves": {
            "majors_production_bound": majors_summary,
            "ten_u_local_experiment": ten_u_summary,
        },
        "majors_readiness_pointer": majors_readiness_pointer,
        "majors_refresh_status": majors_refresh_status,
        "notes": (
            "Dashboard is local-paper ops only. Demo/live remain late-stage and closed. "
            "majors_readiness_pointer is a snapshot reference, not live trading gate."
        ),
    }
