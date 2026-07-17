"""CLI for the production / paper-prep track."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from prod.admission import (
    AdmissionThresholds,
    admit_ten_u_from_report,
    write_admission_report,
)
from prod.registry import (
    DEFAULT_REGISTRY_PATH,
    PaperPrepEntry,
    load_registry,
    upsert_entry,
)
from prod.ten_u_market_refresh import run_ten_u_market_refresh
from prod.ten_u_paper_runtime import (
    DEFAULT_CYCLE_PATH,
    DEFAULT_STATE_PATH,
    run_paper_cycle,
)
from prod.universe_check import run_universe_check, write_universe_report
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
                    "High-risk 10U paper-prep. Prospective wait not required. "
                    "Live remains closed until separate promotion."
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


def _cmd_status(args: argparse.Namespace) -> int:
    payload = {
        "strategy_id": STRATEGY_ID,
        "registry": load_registry(Path(args.registry)),
        "state_path": args.state,
        "state_exists": Path(args.state).exists(),
        "cycle_path": args.cycle_out,
        "cycle_exists": Path(args.cycle_out).exists(),
    }
    if Path(args.state).exists():
        payload["state"] = json.loads(Path(args.state).read_text(encoding="utf-8"))
    if Path(args.cycle_out).exists():
        payload["last_cycle"] = json.loads(Path(args.cycle_out).read_text(encoding="utf-8"))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


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
    """Refresh public OKX 10U data then run one local paper cycle."""
    refresh_report = run_ten_u_market_refresh(
        Path(args.data),
        Path(args.manifest),
    )
    refresh_out = Path(args.refresh_out)
    refresh_out.parent.mkdir(parents=True, exist_ok=True)
    refresh_out.write_text(json.dumps(refresh_report, indent=2), encoding="utf-8")

    cycle_report = run_paper_cycle(
        data_dir=Path(args.data),
        manifest_path=Path(args.manifest),
        state_path=Path(args.state),
        registry_path=Path(args.registry),
        cycle_path=Path(args.cycle_out),
        lookback_days=args.lookback_days,
        force=args.force,
    )
    combined = {
        "report_type": "ten_u_run_pipeline",
        "formal_status": cycle_report.get("formal_status"),
        "refresh": {
            "formal_status": refresh_report.get("formal_status"),
            "errors": refresh_report.get("errors"),
            "available_through": refresh_report.get("available_through"),
            "candles": {
                k: {
                    "added_bars": v.get("added_bars"),
                    "rows": v.get("rows"),
                    "error": v.get("error"),
                }
                for k, v in (refresh_report.get("candles") or {}).items()
            },
        },
        "paper_cycle": cycle_report,
    }
    pipeline_out = Path(args.pipeline_out)
    pipeline_out.parent.mkdir(parents=True, exist_ok=True)
    pipeline_out.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(json.dumps(combined, indent=2, ensure_ascii=False))
    status = cycle_report.get("formal_status")
    if status == "blocked_not_in_paper_prep_registry":
        return 2
    if status == "halted":
        return 3
    if status not in {"ok"} and status is not None:
        return 1
    return 0


def _cmd_universe_check(args: argparse.Namespace) -> int:
    report = run_universe_check()
    out = Path(args.out)
    write_universe_report(report, out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("formal_status") in {"ok", "partial"} else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m prod.cli",
        description="Production track: paper-prep admission and 10U paper runtime",
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

    status = sub.add_parser("status", help="Show paper-prep registry + 10U paper state")
    status.add_argument("--registry", default=str(DEFAULT_REGISTRY_PATH))
    status.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    status.add_argument("--cycle-out", default=str(DEFAULT_CYCLE_PATH))
    status.set_defaults(func=_cmd_status)

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
        help="Production entry: refresh 10U market data then one local paper cycle",
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
    run.add_argument("--lookback-days", type=int, default=120)
    run.add_argument("--force", action="store_true")
    run.set_defaults(func=_cmd_run_ten_u)

    uni = sub.add_parser(
        "universe-check",
        help="Live public OKX instrument check vs demo tradeability notes",
    )
    uni.add_argument("--out", default="reports/prod/okx_universe_check.json")
    uni.set_defaults(func=_cmd_universe_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
