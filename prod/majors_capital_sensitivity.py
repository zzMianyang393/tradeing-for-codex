"""Capital-sensitivity ladder for the production-bound majors sleeve.

Runs the same frozen rule at the operator ladder equities:
default 10 USDT, and optional 100 / 500 USDT (hard ceiling).
Rejects any equity outside policy. Offline only — no exchange.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable

from prod.majors_account_replay import load_majors_market, replay_majors_account
from prod.majors_contract import MajorsSleeveConfig, STRATEGY_ID
from prod.policy import (
    CAPITAL_SENSITIVITY_LADDER_USDT,
    DEFAULT_START_EQUITY_USDT,
    MAX_START_EQUITY_USDT,
    validate_start_equity,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _compact_account(report: dict[str, Any]) -> dict[str, Any]:
    account = report.get("account") or {}
    return {
        "formal_status": report.get("formal_status"),
        "starting_equity": account.get("starting_equity"),
        "ending_equity": account.get("ending_equity"),
        "trades": account.get("trades"),
        "max_drawdown_fraction": account.get("max_drawdown_fraction"),
        "profit_factor": account.get("profit_factor"),
        "permanent_account_state": account.get("permanent_account_state"),
        "return_fraction": (
            (float(account["ending_equity"]) / float(account["starting_equity"]) - 1.0)
            if account.get("starting_equity") and float(account["starting_equity"]) > 0
            and account.get("ending_equity") is not None
            else None
        ),
        "start_equity_validation": report.get("start_equity_validation"),
        "config_fingerprint": report.get("config_fingerprint"),
        "bars_common": report.get("bars_common"),
    }


def run_majors_capital_sensitivity(
    data_dir: Path,
    *,
    equities: Iterable[float] | None = None,
    max_bars: int | None = None,
    require_baseline_10: bool = True,
    config: MajorsSleeveConfig | None = None,
    market: dict | None = None,
) -> dict[str, Any]:
    """Replay majors at each equity; always includes policy validation."""
    ladder = tuple(equities) if equities is not None else CAPITAL_SENSITIVITY_LADDER_USDT
    cfg = config or MajorsSleeveConfig()
    rungs: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    shared_market = market if market is not None else load_majors_market(data_dir, cfg)

    for equity in ladder:
        check = validate_start_equity(float(equity))
        if not check.accepted:
            rejected.append(
                {
                    "equity": float(equity),
                    "start_equity_validation": check.to_dict(),
                    "formal_status": "rejected_equity_policy",
                }
            )
            continue
        report = replay_majors_account(
            data_dir,
            config=cfg,
            start_equity=float(equity),
            max_bars=max_bars,
            market=shared_market,
        )
        rungs.append(
            {
                "equity": float(equity),
                "band": check.band,
                "summary": _compact_account(report),
                "full_formal_status": report.get("formal_status"),
            }
        )

    baseline = next(
        (r for r in rungs if abs(r["equity"] - DEFAULT_START_EQUITY_USDT) < 1e-12),
        None,
    )
    formal = "ok"
    reasons: list[str] = []
    if require_baseline_10 and baseline is None:
        formal = "fail"
        reasons.append("missing_10u_baseline_rung")
    elif require_baseline_10 and baseline and baseline["full_formal_status"] != "ok":
        formal = "fail"
        reasons.append("baseline_10u_replay_not_ok")
    elif any(r["full_formal_status"] != "ok" for r in rungs):
        formal = "partial"
        reasons.append("some_rungs_not_ok")
    if rejected:
        formal = "partial" if formal == "ok" else formal
        reasons.append("some_equities_rejected_by_policy")

    return {
        "report_type": "majors_capital_sensitivity",
        "as_of": _utc_now(),
        "formal_status": formal,
        "reasons": reasons,
        "ladder_usdt": list(ladder),
        "max_start_equity_usdt": MAX_START_EQUITY_USDT,
        "default_start_equity_usdt": DEFAULT_START_EQUITY_USDT,
        "strategy_id": cfg.strategy_id,
        "signal_family": getattr(cfg, "signal_family", None),
        "timeframe_minutes": getattr(cfg, "timeframe_minutes", None),
        "config_fingerprint": cfg.fingerprint(),
        "places_exchange_orders": False,
        "live_allowed": False,
        "track_class": "production_bound",
        "rungs": rungs,
        "rejected": rejected,
        "notes": (
            "Capital-sensitivity contrast only. Not trading authorization. "
            "10U baseline must be retained whenever higher equities are reported."
        ),
    }


def write_capital_sensitivity_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
