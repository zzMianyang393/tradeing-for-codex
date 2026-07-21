"""Deep validation for multi_day_momentum_short (batch v2 interesting).

Time OOS split + per-symbol diagnostics. Does not enable trading.
Admission is a separate explicit step only if gates pass.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.majors_account_replay import load_majors_market, replay_majors_account
from prod.majors_capital_sensitivity import run_majors_capital_sensitivity
from prod.majors_contract import primary_majors_config
from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_batch_majors_v2 import research_catalog_v2


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cfg():
    return next(
        c["config"]
        for c in research_catalog_v2()
        if c["name"] == "multi_day_momentum_short"
    )


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    account = report.get("account") or {}
    start = float(account.get("starting_equity") or 0)
    end = float(account.get("ending_equity") or 0)
    ret = (end / start - 1.0) if start > 0 else None
    return {
        "formal_status": report.get("formal_status"),
        "trades": account.get("trades"),
        "starting_equity": start,
        "ending_equity": end,
        "return_fraction": ret,
        "profit_factor": account.get("profit_factor"),
        "max_drawdown_fraction": account.get("max_drawdown_fraction"),
        "permanent_account_state": account.get("permanent_account_state"),
        "bars": report.get("bars_common"),
        "symbols": report.get("symbols"),
    }


def _pass_slice(s: dict[str, Any], *, min_trades: int = 20) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if s.get("formal_status") != "ok":
        return False, ["replay_not_ok"]
    trades = int(s.get("trades") or 0)
    ret = s.get("return_fraction")
    pf = s.get("profit_factor")
    dd = s.get("max_drawdown_fraction")
    if trades < min_trades:
        reasons.append(f"trades_below_{min_trades}")
    if ret is None or float(ret) <= 0:
        reasons.append("non_positive_return")
    if pf is None or float(pf) < 1.0:
        reasons.append("pf_below_1")
    if dd is not None and float(dd) > 0.35:
        reasons.append("drawdown_above_35pct")
    if s.get("permanent_account_state") not in {None, "active"}:
        reasons.append(f"terminal_state_{s.get('permanent_account_state')}")
    return (len(reasons) == 0), reasons


def run_md_mom_short_validation(
    data_dir: Path,
    *,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
    formation_frac: float = 0.60,
    embargo_bars: int = 96,
) -> dict[str, Any]:
    """Formation 60% / OOS 40% with embargo; dual + per-symbol; sensitivity."""
    cfg = _cfg()
    market = load_majors_market(data_dir, primary_majors_config())
    # Full dual common timeline
    ts_sets = [{b.ts for b in bars} for bars in market.values()]
    common = sorted(set.intersection(*ts_sets))
    n = len(common)
    form_end = int(n * formation_frac)
    oos_start = min(n, form_end + embargo_bars)
    formation_ts = common[:form_end]
    oos_ts = common[oos_start:]

    full = _summary(
        replay_majors_account(
            data_dir, config=cfg, start_equity=start_equity, market=market
        )
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

    by_symbol: dict[str, Any] = {}
    for sym in ("BTC-USDT-SWAP", "ETH-USDT-SWAP"):
        by_symbol[sym] = {
            "full": _summary(
                replay_majors_account(
                    data_dir,
                    config=cfg,
                    start_equity=start_equity,
                    market=market,
                    symbol_subset=(sym,),
                )
            ),
            "formation": _summary(
                replay_majors_account(
                    data_dir,
                    config=cfg,
                    start_equity=start_equity,
                    market=market,
                    symbol_subset=(sym,),
                    common_timestamps=formation_ts,
                )
            ),
            "oos": _summary(
                replay_majors_account(
                    data_dir,
                    config=cfg,
                    start_equity=start_equity,
                    market=market,
                    symbol_subset=(sym,),
                    common_timestamps=oos_ts,
                )
            ),
        }

    sens = run_majors_capital_sensitivity(
        data_dir, config=cfg, market=market, max_bars=None
    )
    sens_rungs = [
        {
            "equity": r["equity"],
            "return_fraction": (r.get("summary") or {}).get("return_fraction"),
            "profit_factor": (r.get("summary") or {}).get("profit_factor"),
            "max_drawdown_fraction": (r.get("summary") or {}).get(
                "max_drawdown_fraction"
            ),
            "trades": (r.get("summary") or {}).get("trades"),
            "ending_equity": (r.get("summary") or {}).get("ending_equity"),
        }
        for r in (sens.get("rungs") or [])
    ]

    # Gates (strict for paper-prep recommendation)
    form_ok, form_reasons = _pass_slice(formation, min_trades=30)
    oos_ok, oos_reasons = _pass_slice(oos, min_trades=20)
    full_ok, full_reasons = _pass_slice(full, min_trades=30)

    btc_oos_ok, btc_oos_r = _pass_slice(
        by_symbol["BTC-USDT-SWAP"]["oos"], min_trades=10
    )
    eth_oos_ok, eth_oos_r = _pass_slice(
        by_symbol["ETH-USDT-SWAP"]["oos"], min_trades=10
    )
    # At least one symbol OOS positive-ish (relaxed: ret>0 and pf>=1) OR both not catastrophic
    symbol_oos_pass = btc_oos_ok or eth_oos_ok
    symbol_note: list[str] = []
    if not btc_oos_ok:
        symbol_note.append(f"btc_oos_fail:{btc_oos_r}")
    if not eth_oos_ok:
        symbol_note.append(f"eth_oos_fail:{eth_oos_r}")

    sens_ok = all(
        (r.get("return_fraction") is not None and float(r["return_fraction"]) > 0)
        for r in sens_rungs
    ) and len(sens_rungs) >= 1

    gates = {
        "full_sample_pass": full_ok,
        "full_sample_reasons": full_reasons,
        "formation_pass": form_ok,
        "formation_reasons": form_reasons,
        "oos_pass": oos_ok,
        "oos_reasons": oos_reasons,
        "symbol_oos_any_pass": symbol_oos_pass,
        "symbol_notes": symbol_note,
        "capital_sensitivity_all_positive": sens_ok,
    }

    # Paper-prep recommendation (still not auto-trading)
    blockers: list[str] = []
    if not full_ok:
        blockers.append("full_sample_gate")
    if not form_ok:
        blockers.append("formation_gate")
    if not oos_ok:
        blockers.append("oos_gate")
    if not symbol_oos_pass:
        blockers.append("no_symbol_oos_pass")
    if not sens_ok:
        blockers.append("capital_sensitivity_gate")

    if not blockers:
        decision = "recommend_paper_prep_local_only"
        decision_notes = [
            "All validation gates passed under frozen rule.",
            "Paper-prep is local only; demo/live remain server-later and closed.",
            "Do not change parameters after this validation.",
        ]
    elif oos_ok and full_ok and sens_ok:
        decision = "conditional_watchlist"
        decision_notes = [
            "Core dual OOS/full/sensitivity OK but symbol split incomplete.",
            "May paper with force only after manual review.",
            *blockers,
        ]
    else:
        decision = "reject_for_paper_prep"
        decision_notes = [
            "Failed one or more validation gates.",
            *blockers,
            "Do not grid-search this shell; archive as limited positive full-sample evidence only.",
        ]

    return {
        "report_type": "md_mom_short_deep_validation_v1",
        "as_of": _utc_now(),
        "strategy_id": cfg.strategy_id,
        "signal_family": cfg.signal_family,
        "config_fingerprint": cfg.fingerprint(),
        "split": {
            "formation_frac": formation_frac,
            "embargo_bars": embargo_bars,
            "common_bars": n,
            "formation_bars": len(formation_ts),
            "oos_bars": len(oos_ts),
            "formation_ts_range": [formation_ts[0], formation_ts[-1]]
            if formation_ts
            else [],
            "oos_ts_range": [oos_ts[0], oos_ts[-1]] if oos_ts else [],
        },
        "full_sample": full,
        "formation": formation,
        "oos": oos,
        "by_symbol": by_symbol,
        "capital_sensitivity": {"formal_status": sens.get("formal_status"), "rungs": sens_rungs},
        "gates": gates,
        "decision": decision,
        "decision_notes": decision_notes,
        "blockers": blockers,
        "places_exchange_orders": False,
        "live_allowed": False,
        "ready_for_demo": False,
        "ready_for_live": False,
        "paper_prep_recommended": decision == "recommend_paper_prep_local_only",
    }


def write_validation_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
