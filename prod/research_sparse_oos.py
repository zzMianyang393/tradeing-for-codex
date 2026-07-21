"""Generic formation/OOS validation for sparse majors research configs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from prod.majors_account_replay import load_majors_market, replay_majors_account
from prod.majors_contract import MajorsSleeveConfig
from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_batch_majors_v3 import research_catalog_v3
from prod.research_batch_majors_v4 import research_catalog_v4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    account = report.get("account") or {}
    start = float(account.get("starting_equity") or 0)
    end = float(account.get("ending_equity") or 0)
    ret = (end / start - 1.0) if start > 0 else None
    return {
        "formal_status": report.get("formal_status"),
        "trades": account.get("trades"),
        "return_fraction": ret,
        "ending_equity": end,
        "profit_factor": account.get("profit_factor"),
        "max_drawdown_fraction": account.get("max_drawdown_fraction"),
        "permanent_account_state": account.get("permanent_account_state"),
        "bars": report.get("bars_common"),
    }


def _pass(s: dict[str, Any], min_trades: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if s.get("formal_status") != "ok":
        return False, ["replay_not_ok"]
    if int(s.get("trades") or 0) < min_trades:
        reasons.append(f"trades_below_{min_trades}")
    ret = s.get("return_fraction")
    pf = s.get("profit_factor")
    if ret is None or float(ret) <= 0:
        reasons.append("non_positive_return")
    if pf is None or float(pf) < 1.0:
        reasons.append("pf_below_1")
    return len(reasons) == 0, reasons


def validate_config(
    data_dir: Path,
    cfg: MajorsSleeveConfig,
    *,
    name: str,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
    formation_frac: float = 0.60,
    embargo_bars: int | None = None,
    min_form_trades: int = 15,
    min_oos_trades: int = 10,
) -> dict[str, Any]:
    market = load_majors_market(data_dir, cfg)
    ts_sets = [{b.ts for b in bars} for bars in market.values()]
    common = sorted(set.intersection(*ts_sets)) if len(ts_sets) > 1 else sorted(next(iter(ts_sets)))
    n = len(common)
    if embargo_bars is None:
        # ~1 day on 15m, 1 bar on daily
        embargo_bars = max(1, (1440 // max(1, cfg.timeframe_minutes)))
    form_end = int(n * formation_frac)
    oos_start = min(n, form_end + embargo_bars)
    formation_ts = common[:form_end]
    oos_ts = common[oos_start:]

    full = _summary(
        replay_majors_account(data_dir, config=cfg, start_equity=start_equity, market=market)
    )
    formation = _summary(
        replay_majors_account(
            data_dir,
            config=cfg,
            start_equity=start_equity,
            market=market,
            common_timestamps=formation_ts,
        )
    )
    oos = _summary(
        replay_majors_account(
            data_dir,
            config=cfg,
            start_equity=start_equity,
            market=market,
            common_timestamps=oos_ts,
        )
    )
    f_ok, f_r = _pass(formation, min_form_trades)
    o_ok, o_r = _pass(oos, min_oos_trades)
    full_ok, full_r = _pass(full, min_form_trades)

    blockers: list[str] = []
    if not full_ok:
        blockers.append("full_sample")
    if not f_ok:
        blockers.append("formation")
    if not o_ok:
        blockers.append("oos")

    if not blockers:
        decision = "recommend_paper_prep_local_only"
    elif o_ok and full_ok:
        decision = "conditional_watchlist"
    else:
        decision = "reject_for_paper_prep"

    return {
        "name": name,
        "strategy_id": cfg.strategy_id,
        "signal_family": cfg.signal_family,
        "timeframe_minutes": cfg.timeframe_minutes,
        "config_fingerprint": cfg.fingerprint(),
        "split": {
            "formation_frac": formation_frac,
            "embargo_bars": embargo_bars,
            "common_bars": n,
            "formation_bars": len(formation_ts),
            "oos_bars": len(oos_ts),
        },
        "full_sample": full,
        "formation": formation,
        "oos": oos,
        "gates": {
            "full_pass": full_ok,
            "full_reasons": full_r,
            "formation_pass": f_ok,
            "formation_reasons": f_r,
            "oos_pass": o_ok,
            "oos_reasons": o_r,
        },
        "decision": decision,
        "blockers": blockers,
        "paper_prep_recommended": decision == "recommend_paper_prep_local_only",
        "places_exchange_orders": False,
        "live_allowed": False,
    }


def run_weekly_candidates_oos(data_dir: Path) -> dict[str, Any]:
    """OOS for v3 weekly interesting names (15m proxy)."""
    want = {"weekly_mom_short", "dual_weekly_mom_short"}
    cat = [c for c in research_catalog_v3() if c["name"] in want]
    results = [
        validate_config(
            data_dir,
            c["config"],
            name=c["name"],
            min_form_trades=10,
            min_oos_trades=8,
        )
        for c in cat
    ]
    return {
        "report_type": "sparse_weekly_oos_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "results": results,
        "places_exchange_orders": False,
        "live_allowed": False,
        "notes": [
            "Validation of batch-v3 weakly interesting weekly shorts.",
            "Low trade counts expected; gates may fail on sample size.",
        ],
    }


def run_v4_interesting_oos(data_dir: Path, names: list[str] | None = None) -> dict[str, Any]:
    cat = research_catalog_v4()
    if names:
        cat = [c for c in cat if c["name"] in set(names)]
    results = [
        validate_config(
            data_dir,
            c["config"],
            name=c["name"],
            min_form_trades=12,
            min_oos_trades=8,
            embargo_bars=1,
        )
        for c in cat
    ]
    return {
        "report_type": "native_daily_oos_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "results": results,
        "places_exchange_orders": False,
        "live_allowed": False,
    }


def write_json(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
