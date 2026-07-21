"""Research batch v3: dual-confirm + weekly/streak sparse structures.

Does not retune multi_day_momentum_short; dual_* is a new pre-registered family.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.majors_account_replay import load_majors_market, replay_majors_account
from prod.majors_contract import TRACK_RESEARCH, MajorsSleeveConfig, primary_majors_config
from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_batch_majors import _classify, _compact_account


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cand(
    strategy_id: str,
    signal_family: str,
    *,
    max_hold_bars: int = 288,
    stop_atr: float = 3.0,
    take_profit_atr: float = 4.0,
    risk_per_trade: float = 0.08,
    trailing_atr: float = 2.5,
    max_leverage: float = 3.0,
) -> MajorsSleeveConfig:
    return MajorsSleeveConfig(
        strategy_id=strategy_id,
        track=TRACK_RESEARCH,
        start_equity=DEFAULT_START_EQUITY_USDT,
        signal_family=signal_family,
        risk_per_trade=risk_per_trade,
        max_margin_fraction=0.40,
        max_leverage=max_leverage,
        stop_atr=stop_atr,
        take_profit_atr=take_profit_atr,
        trailing_atr=trailing_atr,
        max_hold_bars=max_hold_bars,
        ruin_equity=2.0,
        peak_drawdown_halt=0.70,
    )


def research_catalog_v3() -> list[dict[str, Any]]:
    return [
        {
            "name": "dual_md_mom_short",
            "hypothesis": "Both BTC and ETH print multi-day down-momentum short same day",
            "config": _cand(
                "prod_majors_dual_md_mom_short_v1",
                "dual_md_mom_short",
            ),
        },
        {
            "name": "dual_md_mom_long",
            "hypothesis": "Both majors multi-day up-momentum long same day",
            "config": _cand(
                "prod_majors_dual_md_mom_long_v1",
                "dual_md_mom_long",
            ),
        },
        {
            "name": "dual_daily_breakout_short",
            "hypothesis": "Both majors daily breakdown short same UTC day",
            "config": _cand(
                "prod_majors_dual_daily_bo_short_v1",
                "dual_daily_breakout_short",
                max_hold_bars=192,
            ),
        },
        {
            "name": "dual_daily_breakout_long",
            "hypothesis": "Both majors daily breakout long same UTC day",
            "config": _cand(
                "prod_majors_dual_daily_bo_long_v1",
                "dual_daily_breakout_long",
                max_hold_bars=192,
            ),
        },
        {
            "name": "dual_streak_down_short",
            "hypothesis": "Both majors 3-day down streak short",
            "config": _cand(
                "prod_majors_dual_streak_down_short_v1",
                "dual_streak_down_short",
            ),
        },
        {
            "name": "dual_weekly_mom_short",
            "hypothesis": "Both majors Monday weekly down-momentum short",
            "config": _cand(
                "prod_majors_dual_weekly_mom_short_v1",
                "dual_weekly_mom_short",
                max_hold_bars=384,
                stop_atr=3.5,
                take_profit_atr=5.0,
            ),
        },
        {
            "name": "streak_down_days_short",
            "hypothesis": "Single-name 3 consecutive down days short (control)",
            "config": _cand(
                "prod_majors_streak_down_short_v1",
                "streak_down_days_short",
            ),
        },
        {
            "name": "streak_up_days_long",
            "hypothesis": "Single-name 3 consecutive up days long (control)",
            "config": _cand(
                "prod_majors_streak_up_long_v1",
                "streak_up_days_long",
            ),
        },
        {
            "name": "weekly_mom_short",
            "hypothesis": "Monday weekly momentum short (control)",
            "config": _cand(
                "prod_majors_weekly_mom_short_v1",
                "weekly_mom_short",
                max_hold_bars=384,
            ),
        },
        {
            "name": "weekly_mom_long",
            "hypothesis": "Monday weekly momentum long (control)",
            "config": _cand(
                "prod_majors_weekly_mom_long_v1",
                "weekly_mom_long",
                max_hold_bars=384,
            ),
        },
    ]


def run_majors_research_batch_v3(
    data_dir: Path,
    *,
    max_bars: int | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    catalog = research_catalog_v3()
    market = load_majors_market(data_dir, primary_majors_config())
    rows: list[dict[str, Any]] = []

    for item in catalog:
        cfg: MajorsSleeveConfig = item["config"]
        if abs(start_equity - cfg.start_equity) > 1e-12:
            from prod.majors_account_replay import _config_with_equity

            cfg = _config_with_equity(cfg, start_equity)
        report = replay_majors_account(
            data_dir,
            config=cfg,
            start_equity=start_equity,
            max_bars=max_bars,
            market=market,
        )
        summary = _compact_account(report)
        summary["signal_family"] = cfg.signal_family
        summary["name"] = item["name"]
        summary["hypothesis"] = item["hypothesis"]
        summary["baseline"] = False
        decision, reasons = _classify(summary)
        summary["research_decision"] = decision
        summary["reasons"] = reasons
        rows.append(summary)

    def sort_key(r: dict[str, Any]) -> tuple:
        ret = r.get("return_fraction")
        pf = r.get("profit_factor")
        return (
            0 if r.get("formal_status") == "ok" else 1,
            -(float(ret) if ret is not None else -999.0),
            -(float(pf) if pf is not None and float(pf) < 1e8 else 0.0),
        )

    ranked = sorted(rows, key=sort_key)
    interesting = [r for r in rows if r["research_decision"] == "interesting_not_admitted"]
    watchlist = [r for r in rows if r["research_decision"] == "watchlist_weak"]

    return {
        "report_type": "majors_research_batch_v3",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "theme": "dual_confirm_and_calendar_sparse",
        "universe": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        "start_equity": start_equity,
        "max_bars": max_bars,
        "candidate_count": len(rows),
        "places_exchange_orders": False,
        "live_allowed": False,
        "ready_for_demo": False,
        "ready_for_live": False,
        "interesting": [r["name"] for r in interesting],
        "watchlist_weak": [r["name"] for r in watchlist],
        "ranking": [
            {
                "name": r["name"],
                "strategy_id": r["strategy_id"],
                "signal_family": r["signal_family"],
                "trades": r["trades"],
                "return_fraction": r["return_fraction"],
                "profit_factor": r["profit_factor"],
                "max_drawdown_fraction": r["max_drawdown_fraction"],
                "ending_equity": r["ending_equity"],
                "research_decision": r["research_decision"],
            }
            for r in ranked
        ],
        "results": rows,
        "notes": [
            "Batch v3: dual-confirm (both majors agree) + weekly/streak controls.",
            "Does not retune multi_day_momentum_short parameters.",
            "Interesting != paper admission.",
        ],
    }


def write_batch_v3_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
