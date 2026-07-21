"""Local readiness package for production-bound majors sleeve.

Bundles: primary fingerprint, capital sensitivity (10/100/500), conservative
side-by-side compare, paper ops/graduation, admission notes.

Never enables demo/live. Not a trading authorization.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.graduation import evaluate_from_runtime_files
from prod.majors_account_replay import (
    load_majors_market,
    replay_majors_account,
)
from prod.majors_capital_sensitivity import run_majors_capital_sensitivity
from prod.majors_contract import (
    CONSERVATIVE_STRATEGY_ID,
    STRATEGY_ID,
    MajorsSleeveConfig,
    conservative_majors_config,
    primary_majors_config,
)
from prod.majors_paper_runtime import DEFAULT_CYCLE_PATH, DEFAULT_STATE_PATH
from prod.majors_pipeline import majors_data_preflight
from prod.ops_summary import build_sleeve_ops_summary
from prod.policy import DEFAULT_START_EQUITY_USDT, operator_policy_snapshot
from prod.registry import DEFAULT_REGISTRY_PATH, get_entry


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _compact_replay(report: dict[str, Any]) -> dict[str, Any]:
    account = report.get("account") or {}
    return {
        "strategy_id": report.get("strategy_id"),
        "formal_status": report.get("formal_status"),
        "config_fingerprint": report.get("config_fingerprint"),
        "track": report.get("track"),
        "starting_equity": account.get("starting_equity"),
        "ending_equity": account.get("ending_equity"),
        "trades": account.get("trades"),
        "max_drawdown_fraction": account.get("max_drawdown_fraction"),
        "profit_factor": account.get("profit_factor"),
        "permanent_account_state": account.get("permanent_account_state"),
        "bars_common": report.get("bars_common"),
        "places_exchange_orders": report.get("places_exchange_orders", False),
        "live_allowed": report.get("live_allowed", False),
    }


def build_admission_notes(
    *,
    primary_10: dict[str, Any],
    conservative_10: dict[str, Any],
    sensitivity: dict[str, Any],
    graduation_decision: str,
    ops_health: str,
) -> list[str]:
    notes = [
        "local_paper_only_no_exchange_orders",
        "demo_live_require_separate_promotion_after_demo_effect",
        f"primary_fingerprint={primary_10.get('config_fingerprint')}",
        f"conservative_fingerprint={conservative_10.get('config_fingerprint')}",
        f"local_graduation={graduation_decision}",
        f"ops_health={ops_health}",
        "10u_baseline_required_whenever_higher_equity_reported",
    ]
    p_end = primary_10.get("ending_equity")
    p_start = primary_10.get("starting_equity") or DEFAULT_START_EQUITY_USDT
    if p_end is not None and float(p_end) < float(p_start):
        notes.append(
            "primary_10u_fingerprint_negative_or_down_vs_start"
            " — infrastructure ok, not alpha evidence"
        )
    c_end = conservative_10.get("ending_equity")
    c_start = conservative_10.get("starting_equity") or DEFAULT_START_EQUITY_USDT
    if c_end is not None and float(c_end) < float(c_start):
        notes.append("conservative_10u_also_down_vs_start_or_negative")
    if sensitivity.get("formal_status") not in {"ok", "partial"}:
        notes.append("capital_sensitivity_incomplete")
    notes.append(
        "conservative_rule_is_comparison_only_not_default_paper_runtime"
    )
    return notes


def build_majors_readiness_package(
    data_dir: Path,
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    cycle_path: Path = DEFAULT_CYCLE_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    max_bars: int | None = None,
    include_conservative: bool = True,
) -> dict[str, Any]:
    primary = primary_majors_config()
    market = load_majors_market(data_dir, primary)
    preflight = majors_data_preflight(data_dir, config=primary)

    primary_replay = replay_majors_account(
        data_dir,
        config=primary,
        start_equity=DEFAULT_START_EQUITY_USDT,
        max_bars=max_bars,
        market=market,
    )
    sensitivity = run_majors_capital_sensitivity(
        data_dir,
        max_bars=max_bars,
        config=primary,
        market=market,
    )

    conservative_block: dict[str, Any] | None = None
    if include_conservative:
        cons = conservative_majors_config()
        cons_replay = replay_majors_account(
            data_dir,
            config=cons,
            start_equity=DEFAULT_START_EQUITY_USDT,
            max_bars=max_bars,
            market=market,
        )
        conservative_block = {
            "role": "side_by_side_comparison_only",
            "strategy_id": CONSERVATIVE_STRATEGY_ID,
            "config": cons.to_dict(),
            "replay_10u": _compact_replay(cons_replay),
            "not_default_paper_runtime": True,
        }

    state = None
    cycle = None
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    if cycle_path.exists():
        cycle = json.loads(cycle_path.read_text(encoding="utf-8"))
    entry = get_entry(STRATEGY_ID, registry_path)
    graduation = evaluate_from_runtime_files(
        state=state,
        cycle_report=cycle,
        registry_entry=entry,
        symbols=list(primary.symbols),
    )
    ops = build_sleeve_ops_summary(
        strategy_id=STRATEGY_ID,
        track_label="majors_production_bound",
        state=state,
        cycle_report=cycle,
        registry_entry=entry,
        graduation=graduation,
        preflight=preflight,
    )

    primary_compact = _compact_replay(primary_replay)
    cons_compact = (
        conservative_block["replay_10u"]
        if conservative_block
        else {"formal_status": "skipped"}
    )
    notes = build_admission_notes(
        primary_10=primary_compact,
        conservative_10=cons_compact if conservative_block else {},
        sensitivity=sensitivity,
        graduation_decision=graduation.decision,
        ops_health=str(ops.get("health")),
    )

    # Ready for local ops if data+primary fingerprint ok and not policy-violating
    ready_local = (
        preflight.get("formal_status") == "ok"
        and primary_replay.get("formal_status") == "ok"
        and ops.get("health") not in {"policy_violation"}
        and not ops.get("live_allowed")
        and not ops.get("places_exchange_orders")
    )
    if ready_local and ops.get("health") == "halted":
        formal = "local_ops_halted"
    elif ready_local:
        formal = "ready_for_local_ops"
    else:
        formal = "not_ready_local"

    return {
        "report_type": "majors_local_readiness_package",
        "as_of": _utc_now(),
        "formal_status": formal,
        "places_exchange_orders": False,
        "live_allowed": False,
        "ready_for_demo": False,
        "ready_for_live": False,
        "operator_policy": operator_policy_snapshot(),
        "preflight": preflight,
        "primary": {
            "strategy_id": STRATEGY_ID,
            "config": primary.to_dict(),
            "replay_10u": primary_compact,
            "capital_sensitivity": {
                "formal_status": sensitivity.get("formal_status"),
                "rungs": sensitivity.get("rungs"),
                "rejected": sensitivity.get("rejected"),
                "reasons": sensitivity.get("reasons"),
            },
        },
        "conservative_compare": conservative_block,
        "paper_ops": ops,
        "local_graduation": graduation.to_dict(),
        "registry_entry": entry,
        "admission_notes": notes,
        "notes": (
            "Package proves local fingerprint + ops wiring only. "
            "Negative 10U fingerprint is allowed for infrastructure. "
            "Never treat as demo/live authorization."
        ),
    }


def write_readiness_package(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
