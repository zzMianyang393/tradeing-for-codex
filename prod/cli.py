"""CLI for the production / paper-prep track."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from prod.admission import (
    AdmissionThresholds,
    admit_from_account_summary,
    admit_ten_u_from_report,
    write_admission_report,
)
from prod.registry import (
    DEFAULT_REGISTRY_PATH,
    PaperPrepEntry,
    get_entry,
    load_registry,
    upsert_entry,
)
from prod.bootstrap_server import run_bootstrap
from prod.research_batch_majors import (
    run_majors_research_batch,
    write_batch_report,
)
from prod.research_batch_majors_v2 import (
    run_majors_research_batch_v2,
    write_batch_v2_report,
)
from prod.research_batch_majors_v3 import (
    run_majors_research_batch_v3,
    write_batch_v3_report,
)
from prod.research_batch_majors_v4 import (
    run_majors_research_batch_v4,
    write_batch_v4_report,
)
from prod.research_batch_majors_v5 import (
    run_majors_research_batch_v5,
    write_batch_v5_report,
)
from prod.research_batch_majors_v6 import (
    run_majors_research_batch_v6,
    write_batch_v6_report,
)
from prod.research_h1_multiwindow_oos import (
    run_h1_multiwindow_oos,
    write_multiwindow_report,
)
from prod.research_v6_oos import run_v6_interesting_oos, write_v6_oos_report
from prod.research_majors_primary_health import (
    run_h4_weekly_regime_diagnosis,
    run_majors_primary_health,
    write_health_report,
)
from prod.research_batch_majors_v7 import (
    run_majors_research_batch_v7,
    write_batch_v7_report,
)
from prod.research_v7_gates import run_v7_gates, write_v7_gates_report
from prod.research_majors_combo import run_majors_combo_research, write_combo_report
from prod.research_sparse_oos import (
    run_v4_interesting_oos,
    run_weekly_candidates_oos,
    write_json as write_sparse_oos_json,
)
from prod.research_md_mom_short_validate import (
    run_md_mom_short_validation,
    write_validation_report,
)
from prod.research_htf_pullback import (
    run_htf_pullback_research,
    write_research_report,
)
from prod.server_handoff import build_server_handoff_contract, write_server_handoff_contract
from prod.demo_execution_drill import run_demo_execution_drill
from prod.graduation import evaluate_from_runtime_files
from prod.majors_account_replay import replay_majors_account, write_majors_replay_report
from prod.majors_capital_sensitivity import (
    run_majors_capital_sensitivity,
    write_capital_sensitivity_report,
)
from prod.majors_contract import MajorsSleeveConfig
from prod.majors_contract import STRATEGY_ID as MAJORS_STRATEGY_ID
from prod.majors_paper_runtime import (
    DEFAULT_CYCLE_PATH as MAJORS_CYCLE_PATH,
    DEFAULT_STATE_PATH as MAJORS_STATE_PATH,
    run_majors_paper_cycle,
)
from prod.demo_stage_checklist import (
    evaluate_demo_stage_checklist,
    write_demo_checklist,
)
from prod.majors_pipeline import (
    majors_data_preflight,
    run_majors_locked_pipeline,
    run_majors_refresh_then_paper,
    run_majors_watch_loop,
)
from prod.majors_readiness import (
    build_majors_readiness_package,
    write_readiness_package,
)
from prod.halt_recovery import recover_paper_state_file
from prod.majors_refresh import run_majors_15m_refresh, write_majors_refresh_report
from prod.majors_refresh_1h import run_majors_1h_refresh, write_majors_1h_refresh_report
from prod.ops_summary import (
    build_prod_ops_dashboard,
    build_sleeve_ops_summary,
    compact_readiness_pointer,
    load_readiness_package_file,
)
from prod.policy import operator_policy_snapshot
from prod.runtime_lock import DEFAULT_LOCK_PATH
from prod.ten_u_market_refresh import run_ten_u_market_refresh
from prod.ten_u_paper_runtime import (
    DEFAULT_CYCLE_PATH,
    DEFAULT_STATE_PATH,
    run_paper_cycle,
)
from prod.universe_check import run_universe_check, write_universe_report
from prod.watch_loop import run_locked_pipeline, run_watch_loop
from ten_u_event_trend_contract_v2 import STRATEGY_ID


def _cmd_admit_ten_u(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    if not report_path.exists():
        # Prefer sealed screen if informal full history missing
        fallbacks = [
            Path("reports/ten_u_event_trend_informal_full_history_v2.json"),
            Path("reports/ten_u_event_trend_screen_v2.json"),
        ]
        for fb in fallbacks:
            if fb.exists():
                report_path = fb
                break
        else:
            print(
                json.dumps(
                    {
                        "error": "no admission source report found",
                        "tried": [args.report, *[str(p) for p in fallbacks]],
                        "hint": "Run informal full replay or sealed screen first",
                    },
                    indent=2,
                )
            )
            return 2

    thr = AdmissionThresholds(
        minimum_trades=args.min_trades,
        minimum_profit_factor=args.min_pf,
        maximum_drawdown_fraction=args.max_dd,
    )
    result = admit_ten_u_from_report(
        report_path,
        accept_concentration_risk=args.accept_concentration_risk,
        high_risk_sleeve=True,
        thresholds=thr,
    )
    out = Path(args.out)
    write_admission_report(result, out)

    if result.paper_prep_allowed and args.register:
        upsert_entry(
            PaperPrepEntry(
                strategy_id=result.strategy_id,
                track="ten_u_high_risk",
                status="paper_prep",
                config_fingerprint=result.config_fingerprint or "",
                admitted_at=result.as_of,
                admission_decision=result.decision,
                warnings=list(result.warnings),
                live_allowed=False,
                notes=(
                    "High-risk 10U local paper-prep. Prospective wait not required. "
                    "Default pipeline places no exchange orders. "
                    "RAVE/LAB universe is local_experiment — not demo/live graduation. "
                    "Live remains closed until separate promotion after demo effect."
                ),
                evidence_paths=[str(report_path), str(out)],
            ),
            Path(args.registry),
        )

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.paper_prep_allowed else 1


def _cmd_registry_list(args: argparse.Namespace) -> int:
    reg = load_registry(Path(args.registry))
    print(json.dumps(reg, indent=2, ensure_ascii=False))
    return 0


def _cmd_paper_cycle(args: argparse.Namespace) -> int:
    report = run_paper_cycle(
        data_dir=Path(args.data),
        manifest_path=Path(args.manifest),
        state_path=Path(args.state),
        registry_path=Path(args.registry),
        cycle_path=Path(args.cycle_out),
        lookback_days=args.lookback_days,
        force=args.force,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report.get("formal_status")
    if status == "blocked_not_in_paper_prep_registry":
        return 2
    if status == "halted":
        return 3
    return 0


def _sleeve_status(
    *,
    strategy_id: str,
    track_label: str,
    registry_path: Path,
    state_path: Path,
    cycle_path: Path,
    preflight: dict | None = None,
) -> dict:
    state = None
    last_cycle = None
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    if cycle_path.exists():
        last_cycle = json.loads(cycle_path.read_text(encoding="utf-8"))
    entry = get_entry(strategy_id, registry_path)
    graduation = evaluate_from_runtime_files(
        state=state,
        cycle_report=last_cycle,
        registry_entry=entry,
        symbols=(state or {}).get("symbols")
        or (last_cycle or {}).get("universe_validation", {}).get("symbols"),
    )
    ops = build_sleeve_ops_summary(
        strategy_id=strategy_id,
        track_label=track_label,
        state=state,
        cycle_report=last_cycle,
        registry_entry=entry,
        graduation=graduation,
        preflight=preflight,
    )
    block = {
        "strategy_id": strategy_id,
        "local_graduation": graduation.to_dict(),
        "ops_summary": ops,
        "state_path": str(state_path),
        "state_exists": state_path.exists(),
        "cycle_path": str(cycle_path),
        "cycle_exists": cycle_path.exists(),
        "registry_entry": entry,
    }
    if state is not None:
        block["state"] = state
    if last_cycle is not None:
        block["last_cycle"] = last_cycle
    return block


def _cmd_status(args: argparse.Namespace) -> int:
    policy = operator_policy_snapshot()
    registry_path = Path(args.registry)
    majors_pre = None
    if args.include_preflight:
        majors_pre = majors_data_preflight(Path(args.majors_data))
    ten_u = _sleeve_status(
        strategy_id=STRATEGY_ID,
        track_label="ten_u_local_experiment",
        registry_path=registry_path,
        state_path=Path(args.state),
        cycle_path=Path(args.cycle_out),
    )
    majors = _sleeve_status(
        strategy_id=MAJORS_STRATEGY_ID,
        track_label="majors_production_bound",
        registry_path=registry_path,
        state_path=Path(args.majors_state),
        cycle_path=Path(args.majors_cycle_out),
        preflight=majors_pre,
    )
    dashboard = build_prod_ops_dashboard(
        majors_summary=majors["ops_summary"],
        ten_u_summary=ten_u["ops_summary"],
    )
    payload = {
        "operator_policy": policy,
        "default_pipeline_places_exchange_orders": policy[
            "default_pipeline_places_exchange_orders"
        ],
        "ops_dashboard": dashboard,
        "registry": load_registry(registry_path),
        "sleeves": {
            "ten_u_local_experiment": ten_u,
            "majors_production_bound": majors,
        },
        # Backward-compatible aliases (legacy 10U)
        "strategy_id": STRATEGY_ID,
        "local_graduation": ten_u["local_graduation"],
        "state_path": args.state,
        "state_exists": ten_u["state_exists"],
        "cycle_path": args.cycle_out,
        "cycle_exists": ten_u["cycle_exists"],
    }
    if "state" in ten_u:
        payload["state"] = ten_u["state"]
    if "last_cycle" in ten_u:
        payload["last_cycle"] = ten_u["last_cycle"]
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_ops_summary(args: argparse.Namespace) -> int:
    """Compact dual-sleeve ops dashboard only."""
    registry_path = Path(args.registry)
    majors_pre = majors_data_preflight(Path(args.majors_data))
    ten_u = _sleeve_status(
        strategy_id=STRATEGY_ID,
        track_label="ten_u_local_experiment",
        registry_path=registry_path,
        state_path=Path(args.state),
        cycle_path=Path(args.cycle_out),
    )
    majors = _sleeve_status(
        strategy_id=MAJORS_STRATEGY_ID,
        track_label="majors_production_bound",
        registry_path=registry_path,
        state_path=Path(args.majors_state),
        cycle_path=Path(args.majors_cycle_out),
        preflight=majors_pre,
    )
    readiness_pkg = None
    if args.rebuild_readiness:
        readiness_pkg = build_majors_readiness_package(
            Path(args.majors_data),
            state_path=Path(args.majors_state),
            cycle_path=Path(args.majors_cycle_out),
            registry_path=registry_path,
            max_bars=args.readiness_max_bars,
            include_conservative=True,
        )
        write_readiness_package(readiness_pkg, Path(args.readiness_path))
    else:
        readiness_pkg = load_readiness_package_file(Path(args.readiness_path))
    pointer = compact_readiness_pointer(readiness_pkg)
    dashboard = build_prod_ops_dashboard(
        majors_summary=majors["ops_summary"],
        ten_u_summary=ten_u["ops_summary"],
        majors_readiness_pointer=pointer,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(dashboard, indent=2, ensure_ascii=False))
    return 0 if dashboard.get("overall_health") in {"ok", "partial", "degraded"} else 1


def _cmd_majors_refresh_15m(args: argparse.Namespace) -> int:
    report = run_majors_15m_refresh(
        Path(args.data),
        commit=args.commit,
        workers=args.workers,
    )
    write_majors_refresh_report(report, Path(args.out))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report.get("formal_status")
    if status in {"ok", "dry_run_pending_commit"}:
        return 0
    return 1


def _cmd_clear_halt(args: argparse.Namespace) -> int:
    report = recover_paper_state_file(
        Path(args.state),
        mode=args.mode,
        start_equity=args.start_equity,
        operator_note=args.note,
        confirm_hard_reset=args.confirm_hard_reset,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_majors_replay(args: argparse.Namespace) -> int:
    report = replay_majors_account(
        Path(args.data),
        start_equity=args.start_equity,
        max_bars=args.max_bars,
    )
    out = Path(args.out)
    write_majors_replay_report(report, out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_admit_majors(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    if not report_path.exists():
        # Generate fingerprint replay first
        report = replay_majors_account(
            Path(args.data),
            start_equity=args.start_equity,
            max_bars=args.max_bars,
        )
        write_majors_replay_report(report, report_path)
    else:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    account = report.get("account")
    if not account:
        print(
            json.dumps(
                {"error": "no account in majors replay report", "path": str(report_path)},
                indent=2,
            )
        )
        return 2
    cfg = MajorsSleeveConfig()
    # Infrastructure fingerprint gates (not alpha approval). Ending equity
    # only needs to stay above ruin-style floor so local paper can be admitted.
    thr = AdmissionThresholds(
        minimum_trades=args.min_trades,
        minimum_profit_factor=args.min_pf,
        maximum_drawdown_fraction=args.max_dd,
        minimum_ending_equity=args.min_ending_equity,
    )
    result = admit_from_account_summary(
        strategy_id=MAJORS_STRATEGY_ID,
        track="production_bound_majors",
        account=account,
        config_fingerprint=report.get("config_fingerprint") or cfg.fingerprint(),
        thresholds=thr,
        accept_concentration_risk=args.accept_concentration_risk,
        high_risk_sleeve=True,
        symbols=list(cfg.symbols),
    )
    out = Path(args.out)
    write_admission_report(result, out)
    if result.paper_prep_allowed and args.register:
        upsert_entry(
            PaperPrepEntry(
                strategy_id=result.strategy_id,
                track="production_bound_majors",
                status="paper_prep",
                config_fingerprint=result.config_fingerprint or cfg.fingerprint(),
                admitted_at=result.as_of,
                admission_decision=result.decision,
                warnings=list(result.warnings),
                live_allowed=False,
                notes=(
                    "Production-bound BTC/ETH local paper-prep. "
                    "Default pipeline places no exchange orders. "
                    "Demo/live remain closed until separate promotion after demo effect."
                ),
                evidence_paths=[str(report_path), str(out)],
            ),
            Path(args.registry),
        )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.paper_prep_allowed else 1


def _cmd_paper_cycle_majors(args: argparse.Namespace) -> int:
    from prod.majors_contract import resolve_sleeve_config

    sid = args.strategy_id
    cfg = resolve_sleeve_config(sid)
    report = run_majors_paper_cycle(
        data_dir=Path(args.data),
        state_path=Path(args.state),
        registry_path=Path(args.registry),
        cycle_path=Path(args.cycle_out),
        force=args.force,
        config=cfg,
        strategy_id=sid,
        funding_filter=args.funding_filter,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report.get("formal_status")
    if status == "blocked_not_in_paper_prep_registry":
        return 2
    if status == "halted":
        return 3
    if status == "ok":
        return 0
    return 1


def _cmd_majors_capital_sensitivity(args: argparse.Namespace) -> int:
    from prod.majors_contract import resolve_sleeve_config

    equities = None
    if args.equities:
        equities = [float(x) for x in args.equities.split(",")]
    sid = getattr(args, "strategy_id", None) or MAJORS_STRATEGY_ID
    cfg = resolve_sleeve_config(sid)
    if cfg is None:
        cfg = MajorsSleeveConfig()
    report = run_majors_capital_sensitivity(
        Path(args.data),
        equities=equities,
        max_bars=args.max_bars,
        config=cfg,
    )
    out = Path(args.out)
    write_capital_sensitivity_report(report, out)
    compact = {
        "report_type": report["report_type"],
        "strategy_id": report.get("strategy_id"),
        "config_fingerprint": report.get("config_fingerprint"),
        "formal_status": report.get("formal_status"),
        "reasons": report.get("reasons"),
        "rungs": [
            {
                "equity": r.get("equity"),
                "band": r.get("band"),
                "trades": (r.get("summary") or {}).get("trades"),
                "return_fraction": (r.get("summary") or {}).get("return_fraction"),
                "profit_factor": (r.get("summary") or {}).get("profit_factor"),
                "max_drawdown_fraction": (r.get("summary") or {}).get(
                    "max_drawdown_fraction"
                ),
                "ending_equity": (r.get("summary") or {}).get("ending_equity"),
                "permanent_account_state": (r.get("summary") or {}).get(
                    "permanent_account_state"
                ),
            }
            for r in report.get("rungs") or []
        ],
        "rejected": report.get("rejected"),
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") in {"ok", "partial"} else 1


def _cmd_run_majors(args: argparse.Namespace) -> int:
    from prod.majors_pipeline import default_refresh_fn_for_config, resolve_pipeline_config

    sid = getattr(args, "strategy_id", None) or MAJORS_STRATEGY_ID
    cfg = resolve_pipeline_config(strategy_id=sid)
    refresh_report = None
    if args.refresh_data:
        refresh_impl = default_refresh_fn_for_config(cfg)
        refresh_report = refresh_impl(
            Path(args.data),
            commit=args.commit_refresh,
            workers=1,
        )
        out_refresh = Path(args.refresh_out)
        if cfg.timeframe_minutes == 60:
            write_majors_1h_refresh_report(refresh_report, out_refresh)
        else:
            write_majors_refresh_report(refresh_report, out_refresh)
        if (
            args.commit_refresh
            and refresh_report.get("formal_status") == "fail"
        ):
            print(json.dumps(refresh_report, indent=2, ensure_ascii=False))
            return 1
    try:
        report = run_majors_locked_pipeline(
            data_dir=Path(args.data),
            state_path=Path(args.state),
            registry_path=Path(args.registry),
            cycle_path=Path(args.cycle_out),
            lock_path=Path(args.lock),
            force=args.force,
            skip_preflight=args.skip_preflight,
            strategy_id=sid,
            config=cfg,
            funding_filter=getattr(args, "funding_filter", "none"),
        )
    except TimeoutError as exc:
        payload = {
            "report_type": "majors_locked_pipeline",
            "formal_status": "lock_busy",
            "error": str(exc),
            "places_exchange_orders": False,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 4
    if refresh_report is not None:
        report["data_refresh"] = refresh_report
    out = Path(args.pipeline_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report.get("formal_status")
    if status == "blocked_not_in_paper_prep_registry":
        return 2
    if status == "halted":
        return 3
    if status == "ok":
        return 0
    return 1


def _cmd_watch_majors(args: argparse.Namespace) -> int:
    sid = getattr(args, "strategy_id", None) or MAJORS_STRATEGY_ID
    report = run_majors_watch_loop(
        iterations=args.iterations,
        interval_seconds=args.interval,
        data_dir=Path(args.data),
        state_path=Path(args.state),
        registry_path=Path(args.registry),
        cycle_path=Path(args.cycle_out),
        lock_path=Path(args.lock),
        force=args.force,
        skip_preflight=args.skip_preflight,
        refresh_data=args.refresh_data,
        commit_refresh=args.commit_refresh,
        strategy_id=sid,
        funding_filter=getattr(args, "funding_filter", "none"),
        report_path=Path(args.out),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") in {"ok", "partial"} else 1


def _cmd_majors_hourly(args: argparse.Namespace) -> int:
    """One-shot scheduled job: refresh public bars + local paper for sleeve."""
    sid = getattr(args, "strategy_id", None) or MAJORS_STRATEGY_ID
    try:
        report = run_majors_refresh_then_paper(
            data_dir=Path(args.data),
            state_path=Path(args.state),
            registry_path=Path(args.registry),
            cycle_path=Path(args.cycle_out),
            lock_path=Path(args.lock),
            force=args.force,
            skip_preflight=args.skip_preflight,
            refresh_data=not args.skip_refresh,
            commit_refresh=args.commit_refresh,
            strategy_id=sid,
            funding_filter=getattr(args, "funding_filter", "none"),
        )
    except TimeoutError as exc:
        report = {
            "report_type": "majors_hourly_job",
            "formal_status": "lock_busy",
            "error": str(exc),
            "places_exchange_orders": False,
            "live_allowed": False,
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 4
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report.get("formal_status")
    if status == "ok":
        return 0
    if status == "blocked_not_in_paper_prep_registry":
        return 2
    if status == "halted":
        return 3
    if status == "refresh_fail":
        return 1
    return 1


def _cmd_demo_checklist(args: argparse.Namespace) -> int:
    result = evaluate_demo_stage_checklist(
        data_dir=Path(args.data),
        state_path=Path(args.state),
        cycle_path=Path(args.cycle_out),
        registry_path=Path(args.registry),
        readiness_path=Path(args.readiness_path),
        require_local_graduation=args.require_local_graduation,
        require_demo_credentials=args.require_demo_credentials,
    )
    write_demo_checklist(result, Path(args.out))
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0 if result.eligible_for_stage3_engineering else 1


def _cmd_majors_preflight(args: argparse.Namespace) -> int:
    sid = getattr(args, "strategy_id", None)
    report = majors_data_preflight(Path(args.data), strategy_id=sid)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_majors_refresh_1h(args: argparse.Namespace) -> int:
    report = run_majors_1h_refresh(
        Path(args.data),
        commit=args.commit,
        workers=args.workers,
    )
    write_majors_1h_refresh_report(report, Path(args.out))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("formal_status") == "fail":
        return 1
    if report.get("formal_status") == "dry_run_pending_commit":
        return 0
    return 0


def _cmd_majors_readiness(args: argparse.Namespace) -> int:
    report = build_majors_readiness_package(
        Path(args.data),
        state_path=Path(args.state),
        cycle_path=Path(args.cycle_out),
        registry_path=Path(args.registry),
        max_bars=args.max_bars,
        include_conservative=not args.no_conservative,
    )
    out = Path(args.out)
    write_readiness_package(report, out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report.get("formal_status")
    if status in {"ready_for_local_ops", "local_ops_halted"}:
        return 0
    return 1


def _cmd_refresh_ten_u(args: argparse.Namespace) -> int:
    report = run_ten_u_market_refresh(
        Path(args.data),
        Path(args.manifest),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") in {"ok", "partial"} else 1


def _cmd_run_ten_u(args: argparse.Namespace) -> int:
    """Refresh public OKX 10U data then run one local paper cycle (locked)."""
    try:
        locked = run_locked_pipeline(
            data_dir=Path(args.data),
            manifest_path=Path(args.manifest),
            state_path=Path(args.state),
            registry_path=Path(args.registry),
            cycle_path=Path(args.cycle_out),
            lock_path=Path(args.lock),
            lookback_days=args.lookback_days,
            force=args.force,
        )
    except TimeoutError as exc:
        payload = {
            "report_type": "ten_u_run_pipeline",
            "formal_status": "lock_busy",
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 4

    cycle_report = locked.get("paper_cycle") or {}
    refresh_status = locked.get("refresh_status")
    # Reconstruct a compact refresh summary for the pipeline file
    combined = {
        "report_type": "ten_u_run_pipeline",
        "formal_status": cycle_report.get("formal_status"),
        "lock_path": locked.get("lock_path"),
        "refresh": {
            "formal_status": refresh_status,
            "errors": locked.get("refresh_errors") or [],
            "available_through": locked.get("available_through"),
        },
        "paper_cycle": cycle_report,
    }
    pipeline_out = Path(args.pipeline_out)
    pipeline_out.parent.mkdir(parents=True, exist_ok=True)
    pipeline_out.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    # Also keep last refresh report path for operators who expect the file
    refresh_out = Path(args.refresh_out)
    refresh_out.parent.mkdir(parents=True, exist_ok=True)
    refresh_out.write_text(
        json.dumps(
            {
                "report_type": "ten_u_market_refresh_pointer",
                "formal_status": refresh_status,
                "errors": locked.get("refresh_errors") or [],
                "available_through": locked.get("available_through"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(combined, indent=2, ensure_ascii=False))
    status = cycle_report.get("formal_status")
    if status == "blocked_not_in_paper_prep_registry":
        return 2
    if status == "halted":
        return 3
    if status not in {"ok"} and status is not None:
        return 1
    return 0


def _cmd_watch_ten_u(args: argparse.Namespace) -> int:
    report = run_watch_loop(
        iterations=args.iterations,
        interval_seconds=args.interval,
        data_dir=Path(args.data),
        manifest_path=Path(args.manifest),
        state_path=Path(args.state),
        registry_path=Path(args.registry),
        cycle_path=Path(args.cycle_out),
        lock_path=Path(args.lock),
        lookback_days=args.lookback_days,
        force=args.force,
        report_path=Path(args.out),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report.get("formal_status")
    if status == "ok":
        return 0
    if status == "partial":
        return 0
    return 1


def _cmd_demo_drill(args: argparse.Namespace) -> int:
    report = run_demo_execution_drill(
        symbol=args.symbol,
        confirm_smoke=args.confirm_okx_smoke_order,
        qty=args.qty,
        report_path=Path(args.out),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    status = report.get("formal_status")
    if status in {"readiness_ok", "smoke_ok"}:
        return 0
    if status in {"blocked", "blocked_missing_credentials"}:
        return 2
    return 1


def _cmd_universe_check(args: argparse.Namespace) -> int:
    report = run_universe_check()
    out = Path(args.out)
    write_universe_report(report, out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") in {"ok", "partial"} else 1


def _cmd_bootstrap_server(args: argparse.Namespace) -> int:
    report = run_bootstrap(
        data_dir=Path(args.data) if args.data else None,
        majors_data_dir=Path(args.majors_data),
        registry_path=Path(args.registry),
        skip_download=args.skip_download,
        seed_registry=not args.no_seed_registry,
        force_registry=args.force_registry,
        mode=args.mode,
        history_days=args.history_days,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") in {"ok", "partial"} else 1


def _cmd_server_handoff(args: argparse.Namespace) -> int:
    report = write_server_handoff_contract(Path(args.out))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_research_htf_pullback(args: argparse.Namespace) -> int:
    report = run_htf_pullback_research(
        Path(args.data),
        max_bars=args.max_bars,
        include_baseline_compare=not args.no_baseline,
        include_sensitivity=not args.no_sensitivity,
    )
    write_research_report(report, Path(args.out))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_batch_majors(args: argparse.Namespace) -> int:
    report = run_majors_research_batch(
        Path(args.data),
        max_bars=args.max_bars,
        start_equity=args.start_equity,
    )
    write_batch_report(report, Path(args.out))
    # Compact stdout ranking for operators
    compact = {
        "report_type": report["report_type"],
        "as_of": report["as_of"],
        "formal_status": report["formal_status"],
        "start_equity": report["start_equity"],
        "interesting": report["interesting"],
        "watchlist_weak": report["watchlist_weak"],
        "ranking": report["ranking"],
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_batch_majors_v2(args: argparse.Namespace) -> int:
    report = run_majors_research_batch_v2(
        Path(args.data),
        max_bars=args.max_bars,
        start_equity=args.start_equity,
    )
    write_batch_v2_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "theme": report.get("theme"),
        "as_of": report["as_of"],
        "formal_status": report["formal_status"],
        "start_equity": report["start_equity"],
        "interesting": report["interesting"],
        "watchlist_weak": report["watchlist_weak"],
        "ranking": report["ranking"],
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_batch_majors_v3(args: argparse.Namespace) -> int:
    report = run_majors_research_batch_v3(
        Path(args.data),
        max_bars=args.max_bars,
        start_equity=args.start_equity,
    )
    write_batch_v3_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "theme": report.get("theme"),
        "as_of": report["as_of"],
        "formal_status": report["formal_status"],
        "interesting": report["interesting"],
        "watchlist_weak": report["watchlist_weak"],
        "ranking": report["ranking"],
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_batch_majors_v4(args: argparse.Namespace) -> int:
    report = run_majors_research_batch_v4(
        Path(args.data),
        max_bars=args.max_bars,
        start_equity=args.start_equity,
    )
    write_batch_v4_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "theme": report.get("theme"),
        "as_of": report.get("as_of"),
        "formal_status": report["formal_status"],
        "interesting": report.get("interesting"),
        "watchlist_weak": report.get("watchlist_weak"),
        "ranking": report.get("ranking"),
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_weekly_oos(args: argparse.Namespace) -> int:
    report = run_weekly_candidates_oos(Path(args.data))
    write_sparse_oos_json(report, Path(args.out))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_research_daily_oos(args: argparse.Namespace) -> int:
    names = args.names.split(",") if args.names else None
    report = run_v4_interesting_oos(Path(args.data), names=names)
    write_sparse_oos_json(report, Path(args.out))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_research_batch_majors_v5(args: argparse.Namespace) -> int:
    report = run_majors_research_batch_v5(
        Path(args.data),
        max_bars=args.max_bars,
        start_equity=args.start_equity,
    )
    write_batch_v5_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "theme": report.get("theme"),
        "formal_status": report["formal_status"],
        "interesting": report.get("interesting"),
        "watchlist_weak": report.get("watchlist_weak"),
        "ranking": report.get("ranking"),
        "symbols_loaded": report.get("symbols_loaded"),
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_batch_majors_v6(args: argparse.Namespace) -> int:
    report = run_majors_research_batch_v6(
        Path(args.data),
        max_bars=args.max_bars,
        start_equity=args.start_equity,
    )
    write_batch_v6_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "theme": report.get("theme"),
        "formal_status": report["formal_status"],
        "interesting": report.get("interesting"),
        "watchlist_weak": report.get("watchlist_weak"),
        "ranking": report.get("ranking"),
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_h1_multiwindow_oos(args: argparse.Namespace) -> int:
    fracs = tuple(float(x) for x in args.formation_fracs.split(","))
    report = run_h1_multiwindow_oos(
        Path(args.data),
        start_equity=args.start_equity,
        formation_fracs=fracs,
        embargo_bars=args.embargo_bars,
    )
    write_multiwindow_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "formal_status": report["formal_status"],
        "formation_fracs": report["formation_fracs"],
        "results": [
            {
                "name": r["name"],
                "role": r["role"],
                "aggregate_decision": r["aggregate_decision"],
                "action": r["action"],
                "oos_pass_windows": r["oos_pass_windows"],
                "window_count": r["window_count"],
            }
            for r in report["results"]
        ],
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


def _cmd_research_v6_oos(args: argparse.Namespace) -> int:
    names = args.names.split(",") if args.names else None
    report = run_v6_interesting_oos(
        Path(args.data),
        names=names,
        start_equity=args.start_equity,
        batch_report_path=Path(args.batch_report) if args.batch_report else None,
    )
    write_v6_oos_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "recommended_paper_prep_local_only": report.get(
            "recommended_paper_prep_local_only"
        ),
        "selected_names": report.get("selected_names"),
        "results": [
            {
                "name": r.get("name"),
                "decision": r.get("decision"),
                "blockers": r.get("blockers"),
                "full_return": (r.get("full_sample") or {}).get("return_fraction"),
                "oos_return": (r.get("oos") or {}).get("return_fraction"),
                "oos_pf": (r.get("oos") or {}).get("profit_factor"),
            }
            for r in report.get("results") or []
        ],
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


def _cmd_research_majors_primary_health(args: argparse.Namespace) -> int:
    fracs = tuple(float(x) for x in args.formation_fracs.split(","))
    report = run_majors_primary_health(
        Path(args.data),
        start_equity=args.start_equity,
        formation_fracs=fracs,
        embargo_bars=args.embargo_bars,
        include_capital_ladder=not args.no_capital,
        max_bars_capital=args.max_bars,
    )
    write_health_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "formal_status": report["formal_status"],
        "overall_primary_action": report["overall_primary_action"],
        "sleeves": [
            {
                "name": s["name"],
                "strategy_id": s["strategy_id"],
                "oos_pass_windows": s["oos_pass_windows"],
                "formation_pass_windows": s["formation_pass_windows"],
                "health": s["health"],
            }
            for s in report["sleeves"]
        ],
        "capital_formal_status": (report.get("capital_sensitivity") or {}).get(
            "formal_status"
        ),
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


def _cmd_research_h4_weekly_regime(args: argparse.Namespace) -> int:
    report = run_h4_weekly_regime_diagnosis(
        Path(args.data), start_equity=args.start_equity
    )
    write_health_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "full_sample": report["full_sample"],
        "by_year": report["by_year"],
        "multiwindow": [
            {
                "formation_frac": m["formation_frac"],
                "form_ret": (m["formation"] or {}).get("return_fraction"),
                "oos_ret": (m["oos"] or {}).get("return_fraction"),
                "blockers": m["blockers"],
                "decision": m["decision"],
            }
            for m in report["multiwindow"]
        ],
        "interpretation": report["interpretation"],
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


def _cmd_research_batch_majors_v7(args: argparse.Namespace) -> int:
    report = run_majors_research_batch_v7(
        Path(args.data),
        max_bars=args.max_bars,
        start_equity=args.start_equity,
    )
    write_batch_v7_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "theme": report.get("theme"),
        "formal_status": report["formal_status"],
        "interesting": report.get("interesting"),
        "watchlist_weak": report.get("watchlist_weak"),
        "ranking": report.get("ranking"),
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_majors_combo(args: argparse.Namespace) -> int:
    report = run_majors_combo_research(
        Path(args.data), start_equity=args.start_equity
    )
    write_combo_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "formal_status": report["formal_status"],
        "baseline_primary": {
            "name": (report.get("baseline_primary") or {}).get("name"),
            "return_fraction": (report.get("baseline_primary") or {}).get(
                "return_fraction"
            ),
            "profit_factor": (report.get("baseline_primary") or {}).get("profit_factor"),
            "trades": (report.get("baseline_primary") or {}).get("trades"),
            "max_drawdown_fraction": (report.get("baseline_primary") or {}).get(
                "max_drawdown_fraction"
            ),
        },
        "decision": report.get("decision"),
        "operator_action": report.get("operator_action"),
        "combos_beating_primary_full_sample": report.get(
            "combos_beating_primary_full_sample"
        ),
        "experiment_count": len(report.get("experiments") or []),
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") == "ok" else 1


def _cmd_research_v7_gates(args: argparse.Namespace) -> int:
    names = args.names.split(",") if args.names else None
    fracs = tuple(float(x) for x in args.formation_fracs.split(","))
    report = run_v7_gates(
        Path(args.data),
        names=names,
        start_equity=args.start_equity,
        batch_report_path=Path(args.batch_report) if args.batch_report else None,
        formation_fracs=fracs,
    )
    write_v7_gates_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "recommended_paper_prep_local_only": report.get(
            "recommended_paper_prep_local_only"
        ),
        "results": [
            {
                "name": r.get("name"),
                "decision": r.get("decision"),
                "admit": r.get("admit"),
                "trades": r.get("trades"),
                "full_return": r.get("full_return"),
                "full_pf": r.get("full_pf"),
                "oos_pass_windows": r.get("oos_pass_windows"),
                "formation_pass_windows": r.get("formation_pass_windows"),
            }
            for r in report.get("results") or []
        ],
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0


def _cmd_validate_md_mom_short(args: argparse.Namespace) -> int:
    report = run_md_mom_short_validation(
        Path(args.data),
        start_equity=args.start_equity,
        formation_frac=args.formation_frac,
        embargo_bars=args.embargo_bars,
    )
    write_validation_report(report, Path(args.out))
    compact = {
        "report_type": report["report_type"],
        "decision": report["decision"],
        "paper_prep_recommended": report["paper_prep_recommended"],
        "blockers": report["blockers"],
        "gates": report["gates"],
        "full_sample": report["full_sample"],
        "formation": report["formation"],
        "oos": report["oos"],
        "by_symbol_oos": {
            sym: report["by_symbol"][sym]["oos"]
            for sym in report["by_symbol"]
        },
        "capital_sensitivity": report["capital_sensitivity"],
        "places_exchange_orders": False,
        "live_allowed": False,
        "full_report": str(args.out),
    }
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    return 0 if report["decision"] != "reject_for_paper_prep" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m prod.cli",
        description=(
            "Production track: local paper only by default. "
            "Sleeves: majors BTC/ETH (production-bound) + legacy 10U (local_experiment). "
            "Never place OKX demo/live orders unless demo-drill is invoked explicitly."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    admit = sub.add_parser("admit-ten-u", help="Admit 10U v2 into paper-prep from a backtest report")
    admit.add_argument(
        "--report",
        default="reports/ten_u_event_trend_informal_full_history_v2.json",
        help="Screen or informal full-history JSON",
    )
    admit.add_argument("--out", default="reports/prod/ten_u_admission.json")
    admit.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    admit.add_argument("--register", action="store_true", default=True)
    admit.add_argument("--no-register", action="store_false", dest="register")
    admit.add_argument(
        "--accept-concentration-risk",
        action="store_true",
        default=True,
        help="Allow single-trade dominated equity path for high-risk paper-prep (default on)",
    )
    admit.add_argument("--min-trades", type=int, default=6)
    admit.add_argument("--min-pf", type=float, default=1.0)
    admit.add_argument("--max-dd", type=float, default=0.70)
    admit.set_defaults(func=_cmd_admit_ten_u)

    reg = sub.add_parser("registry", help="Show paper-prep registry")
    reg.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    reg.set_defaults(func=_cmd_registry_list)

    cycle = sub.add_parser("paper-cycle", help="Run one 10U local paper cycle")
    cycle.add_argument("--data", default="data/event_trend_v1")
    cycle.add_argument("--manifest", default="data/event_trend_v1/hourly_dataset_manifest_v1.json")
    cycle.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    cycle.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    cycle.add_argument("--cycle-out", default=str(DEFAULT_CYCLE_PATH))
    cycle.add_argument("--lookback-days", type=int, default=120)
    cycle.add_argument(
        "--force",
        action="store_true",
        help="Run even if strategy is not in registry (debug only)",
    )
    cycle.set_defaults(func=_cmd_paper_cycle)

    status = sub.add_parser(
        "status",
        help="Show operator policy + ten_u local_experiment + majors production-bound sleeves",
    )
    status.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    status.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    status.add_argument("--cycle-out", default=str(DEFAULT_CYCLE_PATH))
    status.add_argument("--majors-state", default=str(MAJORS_STATE_PATH))
    status.add_argument("--majors-cycle-out", default=str(MAJORS_CYCLE_PATH))
    status.add_argument("--majors-data", default="data")
    status.add_argument(
        "--include-preflight",
        action="store_true",
        help="Include majors local data preflight in ops_summary",
    )
    status.set_defaults(func=_cmd_status)

    ops = sub.add_parser(
        "ops-summary",
        help="Compact dual-sleeve local paper ops dashboard (no exchange)",
    )
    ops.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    ops.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    ops.add_argument("--cycle-out", default=str(DEFAULT_CYCLE_PATH))
    ops.add_argument("--majors-state", default=str(MAJORS_STATE_PATH))
    ops.add_argument("--majors-cycle-out", default=str(MAJORS_CYCLE_PATH))
    ops.add_argument("--majors-data", default="data")
    ops.add_argument(
        "--readiness-path",
        default="reports/prod/majors_local_readiness_package.json",
        help="Existing majors-readiness package to attach as pointer",
    )
    ops.add_argument(
        "--rebuild-readiness",
        action="store_true",
        help="Rebuild majors-readiness package before attaching pointer (slower)",
    )
    ops.add_argument("--readiness-max-bars", type=int, default=None)
    ops.add_argument("--out", default="reports/prod/ops_dashboard.json")
    ops.set_defaults(func=_cmd_ops_summary)

    halt = sub.add_parser(
        "clear-halt",
        help=(
            "EXPLICIT local paper halt recovery only "
            "(clear_halt_only|flat_and_clear|hard_reset_paper); never enables live/demo"
        ),
    )
    halt.add_argument(
        "--state",
        default=str(MAJORS_STATE_PATH),
        help="Paper state JSON (default majors)",
    )
    halt.add_argument(
        "--mode",
        choices=["clear_halt_only", "flat_and_clear", "hard_reset_paper"],
        default="clear_halt_only",
    )
    halt.add_argument("--start-equity", type=float, default=10.0)
    halt.add_argument("--note", default="")
    halt.add_argument(
        "--confirm-hard-reset",
        action="store_true",
        help="Required for hard_reset_paper",
    )
    halt.add_argument("--out", default="reports/prod/halt_recovery.json")
    halt.set_defaults(func=_cmd_clear_halt)

    majors_replay = sub.add_parser(
        "majors-replay",
        help="Offline BTC/ETH account fingerprint (default 10U; no exchange)",
    )
    majors_replay.add_argument("--data", default="data")
    majors_replay.add_argument("--start-equity", type=float, default=10.0)
    majors_replay.add_argument(
        "--max-bars",
        type=int,
        default=None,
        help="Optional cap on common timeline bars (for faster debug)",
    )
    majors_replay.add_argument("--out", default="reports/prod/majors_account_replay.json")
    majors_replay.set_defaults(func=_cmd_majors_replay)

    admit_majors = sub.add_parser(
        "admit-majors",
        help="Admit production-bound BTC/ETH sleeve to local paper-prep from majors replay",
    )
    admit_majors.add_argument("--data", default="data")
    admit_majors.add_argument(
        "--report", default="reports/prod/majors_account_replay.json"
    )
    admit_majors.add_argument("--out", default="reports/prod/majors_admission.json")
    admit_majors.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    admit_majors.add_argument("--register", action="store_true", default=True)
    admit_majors.add_argument("--no-register", action="store_false", dest="register")
    admit_majors.add_argument("--start-equity", type=float, default=10.0)
    admit_majors.add_argument("--max-bars", type=int, default=None)
    admit_majors.add_argument("--accept-concentration-risk", action="store_true", default=True)
    admit_majors.add_argument("--min-trades", type=int, default=1)
    admit_majors.add_argument("--min-pf", type=float, default=0.0)
    admit_majors.add_argument("--max-dd", type=float, default=0.99)
    admit_majors.add_argument(
        "--min-ending-equity",
        type=float,
        default=1.0,
        help="Floor for paper-prep (infrastructure); default 1.0 not full 10U recovery",
    )
    admit_majors.set_defaults(func=_cmd_admit_majors)

    majors_cycle = sub.add_parser(
        "paper-cycle-majors",
        help="Run one production-bound BTC/ETH local paper cycle (no exchange orders)",
    )
    majors_cycle.add_argument("--data", default="data")
    majors_cycle.add_argument(
        "--strategy-id",
        default="prod_majors_donchian_atr_long_v1",
        help="Paper sleeve strategy_id (must be paper_prep in registry unless --force)",
    )
    majors_cycle.add_argument(
        "--funding-filter",
        default="none",
        help="none|short_funding_positive|short_funding_negative|...",
    )
    majors_cycle.add_argument("--state", default=str(MAJORS_STATE_PATH))
    majors_cycle.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    majors_cycle.add_argument("--cycle-out", default=str(MAJORS_CYCLE_PATH))
    majors_cycle.add_argument(
        "--force",
        action="store_true",
        help="Run even if strategy is not in registry (debug only)",
    )
    majors_cycle.set_defaults(func=_cmd_paper_cycle_majors)

    sens = sub.add_parser(
        "majors-capital-sensitivity",
        help="Replay majors at 10/100/500 USDT ladder (policy ceiling 500; no exchange)",
    )
    sens.add_argument("--data", default="data")
    sens.add_argument(
        "--strategy-id",
        default=MAJORS_STRATEGY_ID,
        help="Sleeve config (default 15m primary; use admitted research id for 1h)",
    )
    sens.add_argument(
        "--equities",
        default=None,
        help="Comma list, default 10,100,500",
    )
    sens.add_argument("--max-bars", type=int, default=None)
    sens.add_argument(
        "--out", default="reports/prod/majors_capital_sensitivity.json"
    )
    sens.set_defaults(func=_cmd_majors_capital_sensitivity)

    run_m = sub.add_parser(
        "run-majors",
        help="Locked majors pipeline: local data preflight + one paper cycle (no exchange)",
    )
    run_m.add_argument("--data", default="data")
    run_m.add_argument(
        "--strategy-id",
        default=MAJORS_STRATEGY_ID,
        help="Paper sleeve (15m default or admitted 1h research id)",
    )
    run_m.add_argument("--funding-filter", default="none")
    run_m.add_argument("--state", default=str(MAJORS_STATE_PATH))
    run_m.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    run_m.add_argument("--cycle-out", default=str(MAJORS_CYCLE_PATH))
    run_m.add_argument("--lock", default="reports/prod/majors_runtime.lock")
    run_m.add_argument("--pipeline-out", default="reports/prod/majors_run_pipeline.json")
    run_m.add_argument("--force", action="store_true")
    run_m.add_argument("--skip-preflight", action="store_true")
    run_m.add_argument(
        "--refresh-data",
        action="store_true",
        help="Public bar refresh for sleeve timeframe before paper cycle",
    )
    run_m.add_argument(
        "--commit-refresh",
        action="store_true",
        help="Actually append bar rows (requires --refresh-data)",
    )
    run_m.add_argument(
        "--refresh-out", default="reports/prod/majors_refresh.json"
    )
    run_m.set_defaults(func=_cmd_run_majors)

    refresh_m = sub.add_parser(
        "majors-refresh-15m",
        help=(
            "BTC/ETH public 15m incremental refresh (dry-run default; "
            "--commit writes CSVs; never places orders)"
        ),
    )
    refresh_m.add_argument("--data", default="data")
    refresh_m.add_argument(
        "--commit",
        action="store_true",
        help="Commit append to local CSVs",
    )
    refresh_m.add_argument("--workers", type=int, default=1)
    refresh_m.add_argument("--out", default="reports/prod/majors_15m_refresh.json")
    refresh_m.set_defaults(func=_cmd_majors_refresh_15m)

    refresh_1h = sub.add_parser(
        "majors-refresh-1h",
        help=(
            "BTC/ETH public 1H incremental refresh (OKX bar=1H; dry-run default; "
            "--commit writes CSVs; never places orders)"
        ),
    )
    refresh_1h.add_argument("--data", default="data")
    refresh_1h.add_argument(
        "--commit",
        action="store_true",
        help="Commit append to local CSVs",
    )
    refresh_1h.add_argument("--workers", type=int, default=1)
    refresh_1h.add_argument("--out", default="reports/prod/majors_1h_refresh.json")
    refresh_1h.set_defaults(func=_cmd_majors_refresh_1h)

    watch_m = sub.add_parser(
        "watch-majors",
        help="Finite locked majors paper loop (Task Scheduler / cron; no exchange)",
    )
    watch_m.add_argument("--iterations", type=int, default=2)
    watch_m.add_argument("--interval", type=float, default=0.0)
    watch_m.add_argument("--data", default="data")
    watch_m.add_argument(
        "--strategy-id",
        default=MAJORS_STRATEGY_ID,
        help="Paper sleeve (15m default or admitted 1h research id)",
    )
    watch_m.add_argument("--funding-filter", default="none")
    watch_m.add_argument("--state", default=str(MAJORS_STATE_PATH))
    watch_m.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    watch_m.add_argument("--cycle-out", default=str(MAJORS_CYCLE_PATH))
    watch_m.add_argument("--lock", default="reports/prod/majors_runtime.lock")
    watch_m.add_argument("--force", action="store_true")
    watch_m.add_argument("--skip-preflight", action="store_true")
    watch_m.add_argument(
        "--refresh-data",
        action="store_true",
        help="Each iteration: public bar refresh for sleeve TF then paper",
    )
    watch_m.add_argument(
        "--commit-refresh",
        action="store_true",
        help="Commit bar appends when --refresh-data is set",
    )
    watch_m.add_argument("--out", default="reports/prod/majors_watch_loop.json")
    watch_m.set_defaults(func=_cmd_watch_majors)

    hourly = sub.add_parser(
        "majors-hourly",
        help=(
            "Scheduled one-shot: BTC/ETH public bar refresh + locked local paper "
            "(no exchange orders). Timeframe follows --strategy-id. "
            "For Task Scheduler / cron."
        ),
    )
    hourly.add_argument("--data", default="data")
    hourly.add_argument(
        "--strategy-id",
        default=MAJORS_STRATEGY_ID,
        help=(
            "Default 15m donchian; use prod_majors_h1_md_mom_short_v1 for 1h sleeve "
            "(separate --state/--cycle-out recommended)"
        ),
    )
    hourly.add_argument("--funding-filter", default="none")
    hourly.add_argument("--state", default=str(MAJORS_STATE_PATH))
    hourly.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    hourly.add_argument("--cycle-out", default=str(MAJORS_CYCLE_PATH))
    hourly.add_argument("--lock", default="reports/prod/majors_runtime.lock")
    hourly.add_argument("--force", action="store_true")
    hourly.add_argument("--skip-preflight", action="store_true")
    hourly.add_argument("--skip-refresh", action="store_true")
    hourly.add_argument(
        "--commit-refresh",
        action="store_true",
        default=True,
        help="Commit bar append (default on for scheduled job)",
    )
    hourly.add_argument(
        "--no-commit-refresh",
        action="store_false",
        dest="commit_refresh",
    )
    hourly.add_argument("--out", default="reports/prod/majors_hourly_job.json")
    hourly.set_defaults(func=_cmd_majors_hourly)

    demo_chk = sub.add_parser(
        "demo-checklist",
        help=(
            "Stage-3 demo admission checklist (engineering eligibility only; "
            "never enables auto-trading or live)"
        ),
    )
    demo_chk.add_argument("--data", default="data")
    demo_chk.add_argument("--state", default=str(MAJORS_STATE_PATH))
    demo_chk.add_argument("--cycle-out", default=str(MAJORS_CYCLE_PATH))
    demo_chk.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    demo_chk.add_argument(
        "--readiness-path",
        default="reports/prod/majors_local_readiness_package.json",
    )
    demo_chk.add_argument(
        "--require-local-graduation",
        action="store_true",
        help="Fail checklist unless local_graduation=graduated_local",
    )
    demo_chk.add_argument(
        "--require-demo-credentials",
        action="store_true",
        help="Fail checklist unless OKX_* sandbox env vars present",
    )
    demo_chk.add_argument("--out", default="reports/prod/demo_stage3_checklist.json")
    demo_chk.set_defaults(func=_cmd_demo_checklist)

    pre_m = sub.add_parser(
        "majors-preflight",
        help="Local BTC/ETH OHLCV data preflight for sleeve timeframe (no network, no orders)",
    )
    pre_m.add_argument("--data", default="data")
    pre_m.add_argument(
        "--strategy-id",
        default=MAJORS_STRATEGY_ID,
        help="Resolves timeframe (15m vs 1h)",
    )
    pre_m.add_argument("--out", default="reports/prod/majors_data_preflight.json")
    pre_m.set_defaults(func=_cmd_majors_preflight)

    ready = sub.add_parser(
        "majors-readiness",
        help=(
            "Local readiness package: primary 10U fingerprint + 10/100/500 "
            "sensitivity + conservative compare + ops/graduation (no exchange)"
        ),
    )
    ready.add_argument("--data", default="data")
    ready.add_argument("--state", default=str(MAJORS_STATE_PATH))
    ready.add_argument("--cycle-out", default=str(MAJORS_CYCLE_PATH))
    ready.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    ready.add_argument("--max-bars", type=int, default=None)
    ready.add_argument("--no-conservative", action="store_true")
    ready.add_argument(
        "--out", default="reports/prod/majors_local_readiness_package.json"
    )
    ready.set_defaults(func=_cmd_majors_readiness)

    refresh = sub.add_parser(
        "refresh-ten-u",
        help="Refresh RAVE/LAB/ETH 1H candles + funding from OKX public APIs",
    )
    refresh.add_argument("--data", default="data/event_trend_v1")
    refresh.add_argument(
        "--manifest", default="data/event_trend_v1/hourly_dataset_manifest_v1.json"
    )
    refresh.add_argument("--out", default="reports/prod/ten_u_market_refresh.json")
    refresh.set_defaults(func=_cmd_refresh_ten_u)

    run = sub.add_parser(
        "run-ten-u",
        help=(
            "Production entry: refresh 10U market data then one local paper cycle "
            "(no exchange orders)"
        ),
    )
    run.add_argument("--data", default="data/event_trend_v1")
    run.add_argument(
        "--manifest", default="data/event_trend_v1/hourly_dataset_manifest_v1.json"
    )
    run.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    run.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    run.add_argument("--cycle-out", default=str(DEFAULT_CYCLE_PATH))
    run.add_argument("--refresh-out", default="reports/prod/ten_u_market_refresh.json")
    run.add_argument("--pipeline-out", default="reports/prod/ten_u_run_pipeline.json")
    run.add_argument("--lock", default=str(DEFAULT_LOCK_PATH))
    run.add_argument("--lookback-days", type=int, default=120)
    run.add_argument("--force", action="store_true")
    run.set_defaults(func=_cmd_run_ten_u)

    watch = sub.add_parser(
        "watch-ten-u",
        help="Finite locked loop: refresh+paper every interval (for Task Scheduler / cron)",
    )
    watch.add_argument("--iterations", type=int, default=3)
    watch.add_argument(
        "--interval",
        type=float,
        default=0.0,
        help="Seconds between iterations (0 for back-to-back; use 3600 for hourly)",
    )
    watch.add_argument("--data", default="data/event_trend_v1")
    watch.add_argument(
        "--manifest", default="data/event_trend_v1/hourly_dataset_manifest_v1.json"
    )
    watch.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    watch.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    watch.add_argument("--cycle-out", default=str(DEFAULT_CYCLE_PATH))
    watch.add_argument("--lock", default=str(DEFAULT_LOCK_PATH))
    watch.add_argument("--lookback-days", type=int, default=120)
    watch.add_argument("--force", action="store_true")
    watch.add_argument("--out", default="reports/prod/ten_u_watch_loop.json")
    watch.set_defaults(func=_cmd_watch_ten_u)

    demo = sub.add_parser(
        "demo-drill",
        help=(
            "EXPLICIT ONLY: OKX simulated readiness/smoke for ETH/BTC "
            "(never RAVE/LAB; not part of default paper/run pipeline)"
        ),
    )
    demo.add_argument("--symbol", default="ETH-USDT-SWAP")
    demo.add_argument("--qty", type=float, default=0.01)
    demo.add_argument(
        "--confirm-okx-smoke-order",
        action="store_true",
        help="Place far limit + cancel on demo (requires OKX_* env sandbox keys)",
    )
    demo.add_argument("--out", default="reports/prod/demo_execution_drill.json")
    demo.set_defaults(func=_cmd_demo_drill)

    uni = sub.add_parser(
        "universe-check",
        help="Live public OKX instrument check vs demo tradeability notes",
    )
    uni.add_argument("--out", default="reports/prod/okx_universe_check.json")
    uni.set_defaults(func=_cmd_universe_check)

    boot = sub.add_parser(
        "bootstrap-server",
        help=(
            "Cold-start slim checkout (default --mode majors: BTC/ETH 15m + registry). "
            "Does not write API keys."
        ),
    )
    boot.add_argument(
        "--mode",
        choices=["majors", "ten_u", "both"],
        default="majors",
    )
    boot.add_argument(
        "--data",
        default=None,
        help="Legacy ten_u data dir when mode includes ten_u",
    )
    boot.add_argument("--majors-data", default="data")
    boot.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    boot.add_argument("--skip-download", action="store_true")
    boot.add_argument("--no-seed-registry", action="store_true")
    boot.add_argument("--force-registry", action="store_true")
    boot.add_argument("--history-days", type=int, default=120)
    boot.add_argument("--out", default="reports/prod/server_bootstrap.json")
    boot.set_defaults(func=_cmd_bootstrap_server)

    handoff = sub.add_parser(
        "server-handoff",
        help="Write machine-readable server agent handoff contract (no secrets)",
    )
    handoff.add_argument(
        "--out", default="reports/prod/server_handoff_contract.json"
    )
    handoff.set_defaults(func=_cmd_server_handoff)

    research = sub.add_parser(
        "research-htf-pullback",
        help=(
            "Pre-registered BTC/ETH HTF pullback research fingerprint "
            "(10U default; not paper/trading admission)"
        ),
    )
    research.add_argument("--data", default="data")
    research.add_argument("--max-bars", type=int, default=None)
    research.add_argument("--no-baseline", action="store_true")
    research.add_argument("--no-sensitivity", action="store_true")
    research.add_argument(
        "--out", default="reports/prod/research_htf_pullback_v1.json"
    )
    research.set_defaults(func=_cmd_research_htf_pullback)

    batch = sub.add_parser(
        "research-batch-majors",
        help=(
            "Batch pre-registered BTC/ETH 10U candidates (multi-family, one market load; "
            "not paper/trading admission)"
        ),
    )
    batch.add_argument("--data", default="data")
    batch.add_argument("--max-bars", type=int, default=None)
    batch.add_argument("--start-equity", type=float, default=10.0)
    batch.add_argument(
        "--out", default="reports/prod/research_batch_majors_v1.json"
    )
    batch.set_defaults(func=_cmd_research_batch_majors)

    batch2 = sub.add_parser(
        "research-batch-majors-v2",
        help=(
            "Batch v2: low-turnover/sparse BTC/ETH 10U candidates "
            "(daily/4h/slow-cross/squeeze; not paper admission)"
        ),
    )
    batch2.add_argument("--data", default="data")
    batch2.add_argument("--max-bars", type=int, default=None)
    batch2.add_argument("--start-equity", type=float, default=10.0)
    batch2.add_argument(
        "--out", default="reports/prod/research_batch_majors_v2.json"
    )
    batch2.set_defaults(func=_cmd_research_batch_majors_v2)

    batch3 = sub.add_parser(
        "research-batch-majors-v3",
        help=(
            "Batch v3: dual-confirm + weekly/streak sparse BTC/ETH 10U "
            "(not paper admission)"
        ),
    )
    batch3.add_argument("--data", default="data")
    batch3.add_argument("--max-bars", type=int, default=None)
    batch3.add_argument("--start-equity", type=float, default=10.0)
    batch3.add_argument(
        "--out", default="reports/prod/research_batch_majors_v3.json"
    )
    batch3.set_defaults(func=_cmd_research_batch_majors_v3)

    batch4 = sub.add_parser(
        "research-batch-majors-v4",
        help=(
            "Batch v4: native daily (1D) BTC/ETH sparse strategies "
            "(not paper admission)"
        ),
    )
    batch4.add_argument("--data", default="data")
    batch4.add_argument("--max-bars", type=int, default=None)
    batch4.add_argument("--start-equity", type=float, default=10.0)
    batch4.add_argument(
        "--out", default="reports/prod/research_batch_majors_v4.json"
    )
    batch4.set_defaults(func=_cmd_research_batch_majors_v4)

    woos = sub.add_parser(
        "research-weekly-oos",
        help="OOS validate batch-v3 weekly short candidates",
    )
    woos.add_argument("--data", default="data")
    woos.add_argument(
        "--out", default="reports/prod/research_weekly_oos_v1.json"
    )
    woos.set_defaults(func=_cmd_research_weekly_oos)

    doos = sub.add_parser(
        "research-daily-oos",
        help="OOS validate native daily candidates (default: all v4 catalog)",
    )
    doos.add_argument("--data", default="data")
    doos.add_argument(
        "--names",
        default=None,
        help="Comma names from v4 catalog; default all",
    )
    doos.add_argument(
        "--out", default="reports/prod/research_daily_oos_v1.json"
    )
    doos.set_defaults(func=_cmd_research_daily_oos)

    batch5 = sub.add_parser(
        "research-batch-majors-v5",
        help=(
            "Batch v5: native 1h BTC/ETH + optional funding entry filters "
            "(not paper admission)"
        ),
    )
    batch5.add_argument("--data", default="data")
    batch5.add_argument("--max-bars", type=int, default=None)
    batch5.add_argument("--start-equity", type=float, default=10.0)
    batch5.add_argument(
        "--out", default="reports/prod/research_batch_majors_v5.json"
    )
    batch5.set_defaults(func=_cmd_research_batch_majors_v5)

    batch6 = sub.add_parser(
        "research-batch-majors-v6",
        help=(
            "Batch v6: unused 1h families + dual confirms + native 4h "
            "(not paper admission)"
        ),
    )
    batch6.add_argument("--data", default="data")
    batch6.add_argument("--max-bars", type=int, default=None)
    batch6.add_argument("--start-equity", type=float, default=10.0)
    batch6.add_argument(
        "--out", default="reports/prod/research_batch_majors_v6.json"
    )
    batch6.set_defaults(func=_cmd_research_batch_majors_v6)

    h1mw = sub.add_parser(
        "research-h1-multiwindow-oos",
        help=(
            "Multi-window formation/OOS for admitted h1_md_mom_short + dual "
            "(not trading admission)"
        ),
    )
    h1mw.add_argument("--data", default="data")
    h1mw.add_argument("--start-equity", type=float, default=10.0)
    h1mw.add_argument(
        "--formation-fracs",
        default="0.50,0.60,0.70",
        help="Comma formation fractions",
    )
    h1mw.add_argument("--embargo-bars", type=int, default=24)
    h1mw.add_argument(
        "--out", default="reports/prod/research_h1_multiwindow_oos_v1.json"
    )
    h1mw.set_defaults(func=_cmd_research_h1_multiwindow_oos)

    v6oos = sub.add_parser(
        "research-v6-oos",
        help="OOS validate batch-v6 interesting/watchlist (or --names)",
    )
    v6oos.add_argument("--data", default="data")
    v6oos.add_argument("--start-equity", type=float, default=10.0)
    v6oos.add_argument(
        "--names",
        default=None,
        help="Comma names; default interesting+watchlist from batch report",
    )
    v6oos.add_argument(
        "--batch-report",
        default="reports/prod/research_batch_majors_v6.json",
    )
    v6oos.add_argument("--out", default="reports/prod/research_v6_oos_v1.json")
    v6oos.set_defaults(func=_cmd_research_v6_oos)

    health = sub.add_parser(
        "research-majors-primary-health",
        help=(
            "15m primary+conservative multiwindow OOS + capital ladder health "
            "(no orders; registry decision aid)"
        ),
    )
    health.add_argument("--data", default="data")
    health.add_argument("--start-equity", type=float, default=10.0)
    health.add_argument("--formation-fracs", default="0.50,0.60,0.70")
    health.add_argument("--embargo-bars", type=int, default=96)
    health.add_argument("--no-capital", action="store_true")
    health.add_argument("--max-bars", type=int, default=None)
    health.add_argument(
        "--out", default="reports/prod/research_majors_primary_health_v1.json"
    )
    health.set_defaults(func=_cmd_research_majors_primary_health)

    h4reg = sub.add_parser(
        "research-h4-weekly-regime",
        help="Regime diagnosis for h4_weekly_mom_short watchlist (no retune)",
    )
    h4reg.add_argument("--data", default="data")
    h4reg.add_argument("--start-equity", type=float, default=10.0)
    h4reg.add_argument(
        "--out", default="reports/prod/research_h4_weekly_regime_v1.json"
    )
    h4reg.set_defaults(func=_cmd_research_h4_weekly_regime)

    batch7 = sub.add_parser(
        "research-batch-majors-v7",
        help=(
            "Batch v7: structural families (vol regime/session/failed-break/"
            "relative) on 15m/1h/4h (not paper admission)"
        ),
    )
    batch7.add_argument("--data", default="data")
    batch7.add_argument("--max-bars", type=int, default=None)
    batch7.add_argument("--start-equity", type=float, default=10.0)
    batch7.add_argument(
        "--out", default="reports/prod/research_batch_majors_v7.json"
    )
    batch7.set_defaults(func=_cmd_research_batch_majors_v7)

    v7g = sub.add_parser(
        "research-v7-gates",
        help="Multiwindow gates for batch-v7 interesting/watchlist (or --names)",
    )
    v7g.add_argument("--data", default="data")
    v7g.add_argument("--start-equity", type=float, default=10.0)
    v7g.add_argument("--names", default=None, help="Comma names")
    v7g.add_argument(
        "--batch-report",
        default="reports/prod/research_batch_majors_v7.json",
    )
    v7g.add_argument("--formation-fracs", default="0.50,0.60,0.70")
    v7g.add_argument("--out", default="reports/prod/research_v7_gates_v1.json")
    v7g.set_defaults(func=_cmd_research_v7_gates)

    combo = sub.add_parser(
        "research-majors-combo",
        help=(
            "Combo vs primary: independent equal-weight + priority single-slot "
            "(research only; not admission)"
        ),
    )
    combo.add_argument("--data", default="data")
    combo.add_argument("--start-equity", type=float, default=10.0)
    combo.add_argument(
        "--out", default="reports/prod/research_majors_combo_v1.json"
    )
    combo.set_defaults(func=_cmd_research_majors_combo)

    val = sub.add_parser(
        "validate-md-mom-short",
        help=(
            "Deep validate multi_day_momentum_short: formation/OOS, by-symbol, "
            "10/100/500 (not trading admission by itself)"
        ),
    )
    val.add_argument("--data", default="data")
    val.add_argument("--start-equity", type=float, default=10.0)
    val.add_argument("--formation-frac", type=float, default=0.60)
    val.add_argument("--embargo-bars", type=int, default=96)
    val.add_argument(
        "--out", default="reports/prod/research_md_mom_short_validation.json"
    )
    val.set_defaults(func=_cmd_validate_md_mom_short)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
