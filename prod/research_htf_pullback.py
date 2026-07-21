"""Run pre-registered HTF pullback research fingerprint (BTC/ETH, 10U)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.majors_account_replay import load_majors_market, replay_majors_account
from prod.majors_capital_sensitivity import run_majors_capital_sensitivity
from prod.majors_contract import (
    HTF_PULLBACK_STRATEGY_ID,
    htf_pullback_majors_config,
    primary_majors_config,
)
from prod.policy import DEFAULT_START_EQUITY_USDT


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _compact(report: dict[str, Any]) -> dict[str, Any]:
    account = report.get("account") or {}
    start = float(account.get("starting_equity") or 0)
    end = account.get("ending_equity")
    ret = None
    if end is not None and start > 0:
        ret = float(end) / start - 1.0
    return {
        "strategy_id": report.get("strategy_id"),
        "formal_status": report.get("formal_status"),
        "config_fingerprint": report.get("config_fingerprint"),
        "trades": account.get("trades"),
        "starting_equity": account.get("starting_equity"),
        "ending_equity": account.get("ending_equity"),
        "return_fraction": ret,
        "max_drawdown_fraction": account.get("max_drawdown_fraction"),
        "profit_factor": account.get("profit_factor"),
        "permanent_account_state": account.get("permanent_account_state"),
        "bars_common": report.get("bars_common"),
    }


def run_htf_pullback_research(
    data_dir: Path,
    *,
    max_bars: int | None = None,
    include_baseline_compare: bool = True,
    include_sensitivity: bool = True,
) -> dict[str, Any]:
    """Offline research package for htf_pullback vs optional donchian baseline."""
    cfg = htf_pullback_majors_config(DEFAULT_START_EQUITY_USDT)
    market = load_majors_market(data_dir, cfg)

    primary_replay = replay_majors_account(
        data_dir,
        config=cfg,
        start_equity=DEFAULT_START_EQUITY_USDT,
        max_bars=max_bars,
        market=market,
    )
    sensitivity = None
    if include_sensitivity:
        sensitivity = run_majors_capital_sensitivity(
            data_dir,
            config=cfg,
            market=market,
            max_bars=max_bars,
        )

    baseline = None
    if include_baseline_compare:
        base_cfg = primary_majors_config(DEFAULT_START_EQUITY_USDT)
        baseline = _compact(
            replay_majors_account(
                data_dir,
                config=base_cfg,
                start_equity=DEFAULT_START_EQUITY_USDT,
                max_bars=max_bars,
                market=market,
            )
        )

    candidate = _compact(primary_replay)
    decision = "research_insufficient_or_weak"
    reasons: list[str] = []
    if primary_replay.get("formal_status") != "ok":
        reasons.append("replay_not_ok")
    else:
        trades = int(candidate.get("trades") or 0)
        ret = candidate.get("return_fraction")
        pf = candidate.get("profit_factor")
        if trades < 10:
            reasons.append("trades_below_10")
        if ret is not None and ret <= 0:
            reasons.append("non_positive_10u_return")
        if pf is not None and float(pf) < 1.0:
            reasons.append("profit_factor_below_1")
        if not reasons:
            decision = "research_interesting_not_admitted"
            reasons.append("positive_10u_after_costs_needs_paper_and_oos_review")
        elif trades >= 10 and ret is not None and ret > -0.15 and pf is not None and float(pf) >= 0.9:
            decision = "research_watchlist_weak"
            reasons.append("not_strong_enough_for_promotion_keep_as_evidence")

    return {
        "report_type": "majors_htf_pullback_research_v1",
        "as_of": _utc_now(),
        "strategy_id": HTF_PULLBACK_STRATEGY_ID,
        "research_card": "docs/research_majors_htf_pullback_v1_card.md",
        "formal_status": "ok" if primary_replay.get("formal_status") == "ok" else "fail",
        "research_decision": decision,
        "reasons": reasons,
        "places_exchange_orders": False,
        "live_allowed": False,
        "ready_for_demo": False,
        "ready_for_live": False,
        "not_default_paper_runtime": True,
        "config": cfg.to_dict(),
        "candidate_10u": candidate,
        "baseline_donchian_10u": baseline,
        "capital_sensitivity": {
            "formal_status": (sensitivity or {}).get("formal_status"),
            "rungs": (sensitivity or {}).get("rungs"),
            "rejected": (sensitivity or {}).get("rejected"),
        }
        if sensitivity
        else None,
        "notes": [
            "Pre-registered single default rule; no parameter search.",
            "BTC/ETH only; default 10U; sensitivity ladder policy applies.",
            "Negative or weak result is valid research progress.",
            "Does not admit paper or trading by itself.",
        ],
    }


def write_research_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
