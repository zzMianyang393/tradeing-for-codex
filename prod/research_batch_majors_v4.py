"""Research batch v4: native daily (1D) BTC/ETH sparse strategies.

Uses timeframe_minutes=1440 so lookbacks are real days, not 15m proxies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.majors_account_replay import load_majors_market, replay_majors_account
from prod.majors_contract import TRACK_RESEARCH, MajorsSleeveConfig
from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_batch_majors import _classify, _compact_account


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _daily(
    strategy_id: str,
    signal_family: str,
    *,
    max_hold_bars: int = 15,
    stop_atr: float = 2.5,
    take_profit_atr: float = 3.5,
    risk_per_trade: float = 0.08,
    trailing_atr: float = 2.0,
) -> MajorsSleeveConfig:
    return MajorsSleeveConfig(
        strategy_id=strategy_id,
        track=TRACK_RESEARCH,
        start_equity=DEFAULT_START_EQUITY_USDT,
        timeframe_minutes=1440,
        signal_family=signal_family,
        risk_per_trade=risk_per_trade,
        max_margin_fraction=0.40,
        max_leverage=3.0,
        stop_atr=stop_atr,
        take_profit_atr=take_profit_atr,
        trailing_atr=trailing_atr,
        max_hold_bars=max_hold_bars,
        ruin_equity=2.0,
        peak_drawdown_halt=0.70,
        # unused by most daily families but required schema
        donchian_lookback=20,
        htf_slope_bars=5,
        pullback_lookback=3,
    )


def research_catalog_v4() -> list[dict[str, Any]]:
    return [
        {
            "name": "d1_md_mom_short",
            "hypothesis": "Native daily 5d down-momentum short",
            "config": _daily("prod_majors_d1_md_mom_short_v1", "multi_day_momentum_short"),
        },
        {
            "name": "d1_md_mom_long",
            "hypothesis": "Native daily 5d up-momentum long",
            "config": _daily("prod_majors_d1_md_mom_long_v1", "multi_day_momentum_long"),
        },
        {
            "name": "d1_weekly_mom_short",
            "hypothesis": "Native daily Monday weekly momentum short",
            "config": _daily(
                "prod_majors_d1_weekly_mom_short_v1",
                "weekly_mom_short",
                max_hold_bars=20,
            ),
        },
        {
            "name": "d1_weekly_mom_long",
            "hypothesis": "Native daily Monday weekly momentum long",
            "config": _daily(
                "prod_majors_d1_weekly_mom_long_v1",
                "weekly_mom_long",
                max_hold_bars=20,
            ),
        },
        {
            "name": "d1_dual_md_mom_short",
            "hypothesis": "Both majors native daily 5d down-mom short same bar",
            "config": _daily("prod_majors_d1_dual_md_mom_short_v1", "dual_md_mom_short"),
        },
        {
            "name": "d1_dual_weekly_mom_short",
            "hypothesis": "Both majors Monday weekly down-mom short",
            "config": _daily(
                "prod_majors_d1_dual_weekly_mom_short_v1",
                "dual_weekly_mom_short",
                max_hold_bars=20,
            ),
        },
        {
            "name": "d1_streak_down_short",
            "hypothesis": "Native daily 3-down-day streak short",
            "config": _daily("prod_majors_d1_streak_down_short_v1", "streak_down_days_short"),
        },
        {
            "name": "d1_streak_up_long",
            "hypothesis": "Native daily 3-up-day streak long",
            "config": _daily("prod_majors_d1_streak_up_long_v1", "streak_up_days_long"),
        },
        {
            "name": "d1_slow_ema_cross_short",
            "hypothesis": "Native daily ema50/200 death cross short",
            "config": _daily(
                "prod_majors_d1_slow_ema_cross_short_v1",
                "slow_ema_cross_short",
                max_hold_bars=30,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
        },
        {
            "name": "d1_slow_ema_cross_long",
            "hypothesis": "Native daily ema50/200 golden cross long",
            "config": _daily(
                "prod_majors_d1_slow_ema_cross_long_v1",
                "slow_ema_cross_long",
                max_hold_bars=30,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
        },
        {
            "name": "d1_donchian_short",
            "hypothesis": "Native daily donchian breakdown short",
            "config": _daily(
                "prod_majors_d1_donchian_short_v1",
                "donchian_short",
                max_hold_bars=15,
            ),
        },
        {
            "name": "d1_donchian_long",
            "hypothesis": "Native daily donchian breakout long",
            "config": _daily(
                "prod_majors_d1_donchian_long_v1",
                "donchian_breakout",
                max_hold_bars=15,
            ),
        },
    ]


def run_majors_research_batch_v4(
    data_dir: Path,
    *,
    max_bars: int | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    catalog = research_catalog_v4()
    # Load native daily once
    seed = catalog[0]["config"]
    market = load_majors_market(data_dir, seed)
    if len(market) < 2:
        return {
            "report_type": "majors_research_batch_v4",
            "formal_status": "data_missing",
            "errors": ["need BTC and ETH daily bars"],
            "places_exchange_orders": False,
            "live_allowed": False,
        }

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
        summary["timeframe"] = "1d"
        decision, reasons = _classify(summary)
        # Daily sample is short: relax low_trade threshold labeling for watchlist only
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
        "report_type": "majors_research_batch_v4",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "theme": "native_daily_sparse",
        "timeframe_minutes": 1440,
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
            "Native 1D bars (not 15m day proxies).",
            "Data ends ~2026-05-27 for daily files in this repo snapshot.",
            "Interesting != paper admission.",
        ],
    }


def write_batch_v4_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
