"""Local paper halt recovery (explicit operator action).

Never enables live trading or exchange orders.
Supports majors (and generic) paper state JSON.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal

from prod.majors_contract import MajorsSleeveConfig
from prod.policy import DEFAULT_START_EQUITY_USDT, default_pipeline_places_exchange_orders


RecoveryMode = Literal["clear_halt_only", "flat_and_clear", "hard_reset_paper"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def plan_halt_recovery(
    state: dict[str, Any],
    *,
    mode: RecoveryMode,
    start_equity: float | None = None,
) -> dict[str, Any]:
    """Pure plan: what would change. Does not write files."""
    if mode not in {"clear_halt_only", "flat_and_clear", "hard_reset_paper"}:
        return {
            "allowed": False,
            "reason": "unknown_mode",
            "mode": mode,
        }

    halt = state.get("halt_reason")
    if mode == "clear_halt_only" and not halt and not state.get("open_position"):
        # still allowed as no-op clear
        pass

    equity_reset_to = None
    if mode == "hard_reset_paper":
        equity_reset_to = float(
            start_equity if start_equity is not None else DEFAULT_START_EQUITY_USDT
        )

    return {
        "allowed": True,
        "mode": mode,
        "current_halt_reason": halt,
        "will_clear_halt": True,
        "will_close_open_position_without_fill": mode
        in {"flat_and_clear", "hard_reset_paper"},
        "will_wipe_closed_trades": mode == "hard_reset_paper",
        "will_reset_equity": mode == "hard_reset_paper",
        "equity_reset_to": equity_reset_to,
        "live_allowed_after": False,
        "places_exchange_orders_after": False,
        "notes": (
            "Recovery is local paper bookkeeping only. "
            "flat_and_clear drops open position without simulating a fill. "
            "hard_reset_paper wipes trade history and restores start equity."
        ),
    }


def apply_halt_recovery(
    state: dict[str, Any],
    *,
    mode: RecoveryMode,
    start_equity: float | None = None,
    operator_note: str = "",
) -> dict[str, Any]:
    """Return new state dict after recovery (immutable-style: does not mutate input)."""
    plan = plan_halt_recovery(state, mode=mode, start_equity=start_equity)
    if not plan.get("allowed"):
        raise ValueError(plan.get("reason") or "recovery_not_allowed")

    new_state = dict(state)
    history = list(new_state.get("recovery_history") or [])
    history.append(
        {
            "at": _utc_now(),
            "mode": mode,
            "previous_halt_reason": state.get("halt_reason"),
            "previous_equity": state.get("equity"),
            "operator_note": operator_note,
        }
    )

    new_state["halt_reason"] = None
    new_state["live_allowed"] = False
    new_state["places_exchange_orders"] = default_pipeline_places_exchange_orders()
    new_state["mode"] = "local_paper"

    if mode in {"flat_and_clear", "hard_reset_paper"}:
        new_state["open_position"] = None

    if mode == "hard_reset_paper":
        eq = float(
            start_equity
            if start_equity is not None
            else DEFAULT_START_EQUITY_USDT
        )
        new_state["equity"] = eq
        new_state["peak_equity"] = eq
        new_state["closed_trades"] = []
        new_state["completed_cycle_count"] = 0
        new_state["local_graduation_decision"] = "not_yet"
        new_state["local_graduation_graduated"] = False

    new_state["recovery_history"] = history[-50:]  # cap
    new_state["last_recovery_at"] = _utc_now()
    new_state["last_recovery_mode"] = mode
    return new_state


def recover_paper_state_file(
    state_path: Path,
    *,
    mode: RecoveryMode,
    start_equity: float | None = None,
    operator_note: str = "",
    confirm_hard_reset: bool = False,
    config: MajorsSleeveConfig | None = None,
) -> dict[str, Any]:
    """Load, apply recovery, write state. Returns audit report."""
    if mode == "hard_reset_paper" and not confirm_hard_reset:
        return {
            "report_type": "paper_halt_recovery",
            "formal_status": "blocked_needs_confirm_hard_reset",
            "hint": "Pass confirm_hard_reset=True / --confirm-hard-reset",
            "places_exchange_orders": False,
            "live_allowed": False,
        }

    if not state_path.exists():
        return {
            "report_type": "paper_halt_recovery",
            "formal_status": "state_missing",
            "state_path": str(state_path),
            "places_exchange_orders": False,
            "live_allowed": False,
        }

    state = json.loads(state_path.read_text(encoding="utf-8"))
    plan = plan_halt_recovery(state, mode=mode, start_equity=start_equity)
    new_state = apply_halt_recovery(
        state,
        mode=mode,
        start_equity=start_equity
        if start_equity is not None
        else (config.start_equity if config else DEFAULT_START_EQUITY_USDT),
        operator_note=operator_note,
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(new_state, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {
        "report_type": "paper_halt_recovery",
        "formal_status": "ok",
        "as_of": _utc_now(),
        "state_path": str(state_path),
        "plan": plan,
        "equity_after": new_state.get("equity"),
        "halt_reason_after": new_state.get("halt_reason"),
        "places_exchange_orders": False,
        "live_allowed": False,
        "mode_applied": mode,
        "notes": "Local paper recovery complete. Demo/live still closed.",
    }
