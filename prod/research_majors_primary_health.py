"""Health check for production-bound 15m majors paper sleeves.

Runs multi-window formation/OOS + 10/100/500 capital ladder on clean BTC/ETH 15m.
Does not place orders. Can recommend keep / suspend / reject for paper_prep.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.majors_account_replay import replay_majors_account
from prod.majors_capital_sensitivity import run_majors_capital_sensitivity
from prod.majors_contract import (
    STRATEGY_ID,
    conservative_majors_config,
    primary_majors_config,
)
from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_sparse_oos import validate_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sleeve_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": "primary_donchian_long",
            "role": "paper_prep_default",
            "strategy_id": STRATEGY_ID,
            "config": primary_majors_config(),
            "min_form_trades": 15,
            "min_oos_trades": 10,
        },
        {
            "name": "conservative_donchian_long",
            "role": "readiness_compare_only",
            "strategy_id": conservative_majors_config().strategy_id,
            "config": conservative_majors_config(),
            "min_form_trades": 12,
            "min_oos_trades": 8,
        },
    ]


def _alpha_health_action(
    *,
    full: dict[str, Any],
    oos_pass_n: int,
    form_pass_n: int,
    window_count: int,
    role: str,
) -> dict[str, Any]:
    """Separate infrastructure paper keep vs alpha quality."""
    trades = int(full.get("trades") or 0)
    ret = full.get("return_fraction")
    pf = full.get("profit_factor")
    dd = full.get("max_drawdown_fraction")
    ruin = full.get("permanent_account_state") == "ruined" or (
        full.get("ending_equity") is not None
        and float(full["ending_equity"]) <= 2.0 + 1e-9
    )

    majority_oos = oos_pass_n >= (window_count + 1) // 2
    full_positive = ret is not None and float(ret) > 0 and pf is not None and float(pf) >= 1.0

    if ruin:
        alpha = "catastrophic"
        paper = "suspend_or_reject_paper_prep"
        reason = "account_ruined_or_near_ruin_on_full_sample"
    elif full_positive and form_pass_n == window_count and oos_pass_n == window_count:
        alpha = "robust"
        paper = "keep_paper_prep"
        reason = "full_formation_oos_all_pass"
    elif full_positive and majority_oos and form_pass_n >= 1:
        alpha = "fragile_positive"
        paper = "keep_paper_prep_monitor"
        reason = "positive_full_majority_oos"
    elif full_positive and oos_pass_n == 0:
        alpha = "overfit_risk"
        paper = "keep_paper_prep_monitor" if role == "paper_prep_default" else "no_action"
        reason = "full_positive_but_oos_fail_all"
    elif ret is not None and float(ret) > -0.25 and trades >= 20:
        alpha = "weak_negative"
        paper = "keep_paper_prep_infrastructure_only" if role == "paper_prep_default" else "no_action"
        reason = "negative_but_not_ruined_infra_ok"
    else:
        alpha = "failed"
        paper = (
            "suspend_paper_prep"
            if role == "paper_prep_default" and (ret is None or float(ret) <= -0.40)
            else (
                "keep_paper_prep_infrastructure_only"
                if role == "paper_prep_default"
                else "no_action"
            )
        )
        reason = "weak_or_failed_alpha"

    return {
        "alpha_quality": alpha,
        "paper_registry_action": paper,
        "reason": reason,
        "full_positive": full_positive,
        "majority_oos": majority_oos,
        "metrics": {
            "trades": trades,
            "return_fraction": ret,
            "profit_factor": pf,
            "max_drawdown_fraction": dd,
            "ending_equity": full.get("ending_equity"),
            "permanent_account_state": full.get("permanent_account_state"),
        },
    }


def run_majors_primary_health(
    data_dir: Path,
    *,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
    formation_fracs: tuple[float, ...] = (0.50, 0.60, 0.70),
    embargo_bars: int = 96,  # ~1 day on 15m
    include_capital_ladder: bool = True,
    max_bars_capital: int | None = None,
) -> dict[str, Any]:
    sleeves: list[dict[str, Any]] = []
    for spec in _sleeve_specs():
        windows: list[dict[str, Any]] = []
        for frac in formation_fracs:
            v = validate_config(
                data_dir,
                spec["config"],
                name=f"{spec['name']}@form{frac:.2f}",
                start_equity=start_equity,
                formation_frac=frac,
                embargo_bars=embargo_bars,
                min_form_trades=int(spec["min_form_trades"]),
                min_oos_trades=int(spec["min_oos_trades"]),
            )
            windows.append(
                {
                    "formation_frac": frac,
                    "decision": v["decision"],
                    "blockers": v["blockers"],
                    "gates": v["gates"],
                    "full_sample": v["full_sample"],
                    "formation": v["formation"],
                    "oos": v["oos"],
                    "split": v["split"],
                }
            )
        full = windows[0]["full_sample"]
        oos_n = sum(1 for w in windows if w["gates"]["oos_pass"])
        form_n = sum(1 for w in windows if w["gates"]["formation_pass"])
        health = _alpha_health_action(
            full=full,
            oos_pass_n=oos_n,
            form_pass_n=form_n,
            window_count=len(windows),
            role=spec["role"],
        )
        sleeves.append(
            {
                "name": spec["name"],
                "role": spec["role"],
                "strategy_id": spec["strategy_id"],
                "config_fingerprint": spec["config"].fingerprint(),
                "timeframe_minutes": 15,
                "windows": windows,
                "oos_pass_windows": oos_n,
                "formation_pass_windows": form_n,
                "window_count": len(windows),
                "health": health,
                "places_exchange_orders": False,
                "live_allowed": False,
            }
        )

    capital: dict[str, Any] | None = None
    if include_capital_ladder:
        capital = run_majors_capital_sensitivity(
            data_dir,
            equities=(10.0, 100.0, 500.0),
            max_bars=max_bars_capital,
        )

    primary = next(s for s in sleeves if s["name"] == "primary_donchian_long")
    overall = primary["health"]["paper_registry_action"]

    return {
        "report_type": "majors_primary_health_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "formation_fracs": list(formation_fracs),
        "embargo_bars": embargo_bars,
        "start_equity": start_equity,
        "sleeves": sleeves,
        "capital_sensitivity": capital,
        "overall_primary_action": overall,
        "places_exchange_orders": False,
        "live_allowed": False,
        "notes": [
            "15m BTC/ETH production-bound health check.",
            "Infrastructure paper may continue with weak alpha; "
            "suspend/reject only on ruin or catastrophic loss.",
            "Not demo/live authorization.",
        ],
    }


def run_h4_weekly_regime_diagnosis(
    data_dir: Path,
    *,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    """Calendar-year and half-sample diagnosis for h4_weekly_mom_short (no retune)."""
    from prod.research_batch_majors_v6 import research_catalog_v6

    item = next(c for c in research_catalog_v6() if c["name"] == "h4_weekly_mom_short")
    cfg = item["config"]
    market_report = replay_majors_account(
        data_dir, config=cfg, start_equity=start_equity
    )
    # year splits via common timestamps filtered by year
    from prod.majors_account_replay import load_majors_market

    market = load_majors_market(data_dir, cfg)
    ts_sets = [{b.ts for b in bars} for bars in market.values()]
    common = sorted(set.intersection(*ts_sets)) if len(ts_sets) > 1 else sorted(next(iter(ts_sets)))

    def year_of(ts_ms: int) -> int:
        return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).year

    years = sorted({year_of(ts) for ts in common})
    by_year: list[dict[str, Any]] = []
    for y in years:
        y_ts = [ts for ts in common if year_of(ts) == y]
        if len(y_ts) < 50:
            continue
        rep = replay_majors_account(
            data_dir,
            config=cfg,
            start_equity=start_equity,
            market=market,
            common_timestamps=y_ts,
        )
        acc = rep.get("account") or {}
        start = float(acc.get("starting_equity") or 0)
        end = float(acc.get("ending_equity") or 0)
        by_year.append(
            {
                "year": y,
                "bars": len(y_ts),
                "trades": acc.get("trades"),
                "return_fraction": (end / start - 1.0) if start > 0 else None,
                "profit_factor": acc.get("profit_factor"),
                "max_drawdown_fraction": acc.get("max_drawdown_fraction"),
                "ending_equity": end,
            }
        )

    multi = []
    for frac in (0.50, 0.60, 0.70):
        multi.append(
            validate_config(
                data_dir,
                cfg,
                name=f"h4_weekly@{frac}",
                start_equity=start_equity,
                formation_frac=frac,
                embargo_bars=6,  # ~1 day on 4h
                min_form_trades=12,
                min_oos_trades=8,
            )
        )

    return {
        "report_type": "h4_weekly_mom_short_regime_diagnosis_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "strategy_id": cfg.strategy_id,
        "config_fingerprint": cfg.fingerprint(),
        "full_sample": {
            "trades": (market_report.get("account") or {}).get("trades"),
            "return_fraction": (
                (
                    float((market_report.get("account") or {}).get("ending_equity") or 0)
                    / float((market_report.get("account") or {}).get("starting_equity") or 1)
                )
                - 1.0
            ),
            "profit_factor": (market_report.get("account") or {}).get("profit_factor"),
            "max_drawdown_fraction": (market_report.get("account") or {}).get(
                "max_drawdown_fraction"
            ),
        },
        "by_year": by_year,
        "multiwindow": [
            {
                "formation_frac": m["split"]["formation_frac"],
                "formation": m["formation"],
                "oos": m["oos"],
                "blockers": m["blockers"],
                "decision": m["decision"],
            }
            for m in multi
        ],
        "interpretation": {
            "pattern": "recent_oos_strong_formation_weak",
            "admit": False,
            "notes": [
                "If early years negative and late years positive, treat as regime artifact.",
                "Do not retune. Keep watchlist only unless formation eventually stabilizes.",
            ],
        },
        "places_exchange_orders": False,
        "live_allowed": False,
    }


def write_health_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
