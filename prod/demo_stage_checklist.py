"""Stage-3 OKX demo admission checklist (engineering gate only).

Evaluating this checklist NEVER enables auto-trading.
Even a full pass only means "eligible to start Stage-3 demo wiring/work",
not that strategy auto-loop or live is authorized.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prod.demo_execution_drill import (
    DEMO_ALLOWED_SYMBOLS,
    credentials_from_env,
    missing_credential_names,
    plan_demo_drill,
)
from prod.majors_contract import STRATEGY_ID, MajorsSleeveConfig
from prod.majors_pipeline import majors_data_preflight
from prod.ops_summary import (
    build_sleeve_ops_summary,
    compact_readiness_pointer,
    load_readiness_package_file,
)
from prod.policy import (
    PRODUCTION_BOUND_SYMBOLS,
    default_pipeline_places_exchange_orders,
    operator_policy_snapshot,
)
from prod.registry import DEFAULT_REGISTRY_PATH, get_entry
from prod.graduation import evaluate_from_runtime_files


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ChecklistItem:
    id: str
    passed: bool
    detail: str
    required_for_pass: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DemoStageChecklistResult:
    decision: str  # eligible_for_stage3_engineering | blocked
    eligible_for_stage3_engineering: bool
    auto_trading_enabled: bool
    places_exchange_orders: bool
    live_allowed: bool
    demo_strategy_loop_enabled: bool
    items: list[ChecklistItem] = field(default_factory=list)
    as_of: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": "demo_stage3_admission_checklist",
            "as_of": self.as_of or _utc_now(),
            "decision": self.decision,
            "eligible_for_stage3_engineering": self.eligible_for_stage3_engineering,
            "auto_trading_enabled": self.auto_trading_enabled,
            "places_exchange_orders": self.places_exchange_orders,
            "live_allowed": self.live_allowed,
            "demo_strategy_loop_enabled": self.demo_strategy_loop_enabled,
            "items": [i.to_dict() for i in self.items],
            "notes": self.notes,
            "operator_policy": operator_policy_snapshot(),
        }


def evaluate_demo_stage_checklist(
    *,
    data_dir: Path = Path("data"),
    state_path: Path = Path("reports/prod/majors_paper_state.json"),
    cycle_path: Path = Path("reports/prod/majors_paper_cycle.json"),
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    readiness_path: Path = Path("reports/prod/majors_local_readiness_package.json"),
    require_local_graduation: bool = False,
    require_demo_credentials: bool = False,
    env: dict[str, str] | None = None,
) -> DemoStageChecklistResult:
    """Pure-ish checklist (may read local files; no exchange orders)."""
    items: list[ChecklistItem] = []
    cfg = MajorsSleeveConfig()

    # 1) Pipeline policy
    places = default_pipeline_places_exchange_orders()
    items.append(
        ChecklistItem(
            id="default_pipeline_no_exchange",
            passed=places is False,
            detail=f"default_pipeline_places_exchange_orders={places}",
        )
    )

    # 2) Universe frozen to BTC/ETH
    uni_ok = set(cfg.symbols) == set(PRODUCTION_BOUND_SYMBOLS)
    items.append(
        ChecklistItem(
            id="production_bound_universe_btc_eth",
            passed=uni_ok,
            detail=f"symbols={list(cfg.symbols)}",
        )
    )

    # 3) Demo allowlist matches production-bound
    demo_ok = set(DEMO_ALLOWED_SYMBOLS) == set(PRODUCTION_BOUND_SYMBOLS)
    items.append(
        ChecklistItem(
            id="demo_allowlist_is_btc_eth",
            passed=demo_ok,
            detail=f"demo_allowed={sorted(DEMO_ALLOWED_SYMBOLS)}",
        )
    )

    # 4) Demo drill plan for ETH (readiness only)
    drill = plan_demo_drill("ETH-USDT-SWAP", confirm_smoke=False)
    items.append(
        ChecklistItem(
            id="demo_drill_eth_readiness_allowed",
            passed=drill.allowed and drill.action == "readiness",
            detail=f"action={drill.action} reason={drill.reason}",
        )
    )

    # 5) Data preflight
    pre = majors_data_preflight(data_dir, config=cfg)
    items.append(
        ChecklistItem(
            id="majors_data_preflight_ok",
            passed=pre.get("formal_status") == "ok",
            detail=f"status={pre.get('formal_status')} errors={pre.get('errors')}",
        )
    )

    # 6) Registry paper_prep for majors
    entry = get_entry(STRATEGY_ID, registry_path)
    reg_ok = bool(entry and entry.get("status") == "paper_prep" and not entry.get("live_allowed"))
    items.append(
        ChecklistItem(
            id="majors_registry_paper_prep",
            passed=reg_ok,
            detail=f"entry_status={(entry or {}).get('status')} live_allowed={(entry or {}).get('live_allowed')}",
        )
    )

    # 7) Ops health
    state = None
    cycle = None
    if state_path.exists():
        import json

        state = json.loads(state_path.read_text(encoding="utf-8"))
    if cycle_path.exists():
        import json

        cycle = json.loads(cycle_path.read_text(encoding="utf-8"))
    grad = evaluate_from_runtime_files(
        state=state,
        cycle_report=cycle,
        registry_entry=entry,
        symbols=list(cfg.symbols),
    )
    ops = build_sleeve_ops_summary(
        strategy_id=STRATEGY_ID,
        track_label="majors_production_bound",
        state=state,
        cycle_report=cycle,
        registry_entry=entry,
        graduation=grad,
        preflight=pre,
    )
    health_ok = ops.get("health") not in {"policy_violation", "halted"}
    items.append(
        ChecklistItem(
            id="ops_health_not_critical",
            passed=health_ok,
            detail=f"health={ops.get('health')} alerts={ops.get('alerts')}",
        )
    )
    items.append(
        ChecklistItem(
            id="ops_live_and_exchange_false",
            passed=(not ops.get("live_allowed") and not ops.get("places_exchange_orders")),
            detail=(
                f"live_allowed={ops.get('live_allowed')} "
                f"places_exchange_orders={ops.get('places_exchange_orders')}"
            ),
        )
    )

    # 8) Readiness package pointer
    pkg = load_readiness_package_file(readiness_path)
    pointer = compact_readiness_pointer(pkg)
    ready_ok = bool(
        pointer
        and pointer.get("formal_status") in {"ready_for_local_ops", "local_ops_halted"}
        and pointer.get("ready_for_demo") is False
        and pointer.get("ready_for_live") is False
    )
    items.append(
        ChecklistItem(
            id="readiness_package_local_only",
            passed=ready_ok,
            detail=(
                f"pointer={None if pointer is None else pointer.get('formal_status')} "
                f"ready_for_demo={None if pointer is None else pointer.get('ready_for_demo')}"
            ),
            required_for_pass=True,
        )
    )

    # 9) Local graduation optional
    grad_ok = grad.decision == "graduated_local"
    items.append(
        ChecklistItem(
            id="local_graduation_graduated_local",
            passed=grad_ok,
            detail=f"decision={grad.decision}",
            required_for_pass=require_local_graduation,
        )
    )

    # 10) Demo credentials optional
    creds = credentials_from_env(env)
    missing = missing_credential_names(creds)
    creds_ok = len(missing) == 0
    items.append(
        ChecklistItem(
            id="demo_sandbox_credentials_present",
            passed=creds_ok,
            detail=f"missing={missing}",
            required_for_pass=require_demo_credentials,
        )
    )

    required_fail = [i for i in items if i.required_for_pass and not i.passed]
    eligible = len(required_fail) == 0

    notes = [
        "Checklist pass does NOT enable demo strategy auto-loop or live trading.",
        "Demo/live execution is server-only; API keys are injected by the server agent, not this workstation.",
        "This checklist is a handoff gate for server-side Stage-3 work, not a local trading license.",
        "Operator must still see demo effect on the server before any live promotion.",
        f"failed_required={[i.id for i in required_fail]}",
    ]

    return DemoStageChecklistResult(
        decision="eligible_for_stage3_engineering" if eligible else "blocked",
        eligible_for_stage3_engineering=eligible,
        auto_trading_enabled=False,
        places_exchange_orders=False,
        live_allowed=False,
        demo_strategy_loop_enabled=False,
        items=items,
        as_of=_utc_now(),
        notes=notes,
    )


def write_demo_checklist(result: DemoStageChecklistResult, path: Path) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
