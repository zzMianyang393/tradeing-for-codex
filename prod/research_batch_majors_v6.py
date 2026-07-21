"""Research batch v6: unused 1h families + dual confirm + native 4h.

Frozen single-default rules only. No parameter search. Not paper admission.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from market import load_market
from prod.majors_account_replay import replay_majors_account
from prod.majors_contract import TRACK_RESEARCH, MajorsSleeveConfig
from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_batch_majors import _classify, _compact_account


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cfg(
    strategy_id: str,
    signal_family: str,
    *,
    timeframe_minutes: int,
    max_hold_bars: int = 48,
    stop_atr: float = 2.5,
    take_profit_atr: float = 3.0,
    risk_per_trade: float = 0.08,
    trailing_atr: float = 2.0,
    donchian_lookback: int = 24,
    htf_slope_bars: int = 24,
    pullback_lookback: int = 4,
) -> MajorsSleeveConfig:
    return MajorsSleeveConfig(
        strategy_id=strategy_id,
        track=TRACK_RESEARCH,
        start_equity=DEFAULT_START_EQUITY_USDT,
        timeframe_minutes=timeframe_minutes,
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
        donchian_lookback=donchian_lookback,
        htf_slope_bars=htf_slope_bars,
        pullback_lookback=pullback_lookback,
    )


def research_catalog_v6() -> list[dict[str, Any]]:
    """Distinct families not primary-covered by v5 md_mom/funding screen."""
    h1 = 60
    h4 = 240
    return [
        # --- 1h dual confirms ---
        {
            "name": "h1_dual_streak_down_short",
            "hypothesis": "1h dual-confirm 3-day down streak short",
            "config": _cfg(
                "prod_majors_h1_dual_streak_down_short_v1",
                "dual_streak_down_short",
                timeframe_minutes=h1,
                max_hold_bars=72,
            ),
        },
        {
            "name": "h1_dual_weekly_mom_short",
            "hypothesis": "1h dual-confirm Monday weekly mom short",
            "config": _cfg(
                "prod_majors_h1_dual_weekly_mom_short_v1",
                "dual_weekly_mom_short",
                timeframe_minutes=h1,
                max_hold_bars=120,
            ),
        },
        {
            "name": "h1_dual_daily_breakout_short",
            "hypothesis": "1h dual-confirm daily-style breakout short",
            "config": _cfg(
                "prod_majors_h1_dual_daily_breakout_short_v1",
                "dual_daily_breakout_short",
                timeframe_minutes=h1,
                max_hold_bars=72,
            ),
        },
        # --- 1h families underused on native 1h ---
        {
            "name": "h1_htf_pullback_short",
            "hypothesis": "1h HTF downtrend + ema20 reject short",
            "config": _cfg(
                "prod_majors_h1_htf_pullback_short_v1",
                "htf_pullback_short",
                timeframe_minutes=h1,
                max_hold_bars=64,
                htf_slope_bars=24,
                pullback_lookback=4,
            ),
        },
        {
            "name": "h1_htf_pullback_long",
            "hypothesis": "1h HTF uptrend + ema20 reclaim long",
            "config": _cfg(
                "prod_majors_h1_htf_pullback_long_v1",
                "htf_pullback",
                timeframe_minutes=h1,
                max_hold_bars=64,
                htf_slope_bars=24,
                pullback_lookback=4,
            ),
        },
        {
            "name": "h1_4h_close_trend_short",
            "hypothesis": "1h bars: 4h-close-equivalent trend short",
            "config": _cfg(
                "prod_majors_h1_4h_close_trend_short_v1",
                "four_h_close_trend_short",
                timeframe_minutes=h1,
                max_hold_bars=48,
            ),
        },
        {
            "name": "h1_4h_close_trend_long",
            "hypothesis": "1h bars: 4h-close-equivalent trend long",
            "config": _cfg(
                "prod_majors_h1_4h_close_trend_long_v1",
                "four_h_close_trend_long",
                timeframe_minutes=h1,
                max_hold_bars=48,
            ),
        },
        {
            "name": "h1_atr_squeeze_short",
            "hypothesis": "1h ATR squeeze breakdown short",
            "config": _cfg(
                "prod_majors_h1_atr_squeeze_short_v1",
                "atr_squeeze_breakout_short",
                timeframe_minutes=h1,
                max_hold_bars=48,
            ),
        },
        {
            "name": "h1_atr_squeeze_long",
            "hypothesis": "1h ATR squeeze breakout long",
            "config": _cfg(
                "prod_majors_h1_atr_squeeze_long_v1",
                "atr_squeeze_breakout_long",
                timeframe_minutes=h1,
                max_hold_bars=48,
            ),
        },
        {
            "name": "h1_daily_breakout_short",
            "hypothesis": "1h daily-style breakout short",
            "config": _cfg(
                "prod_majors_h1_daily_breakout_short_v1",
                "daily_breakout_short",
                timeframe_minutes=h1,
                max_hold_bars=72,
            ),
        },
        {
            "name": "h1_daily_breakout_long",
            "hypothesis": "1h daily-style breakout long",
            "config": _cfg(
                "prod_majors_h1_daily_breakout_long_v1",
                "daily_breakout_long",
                timeframe_minutes=h1,
                max_hold_bars=72,
            ),
        },
        {
            "name": "h1_rsi_trend_short",
            "hypothesis": "1h RSI trend short",
            "config": _cfg(
                "prod_majors_h1_rsi_trend_short_v1",
                "rsi_trend_short",
                timeframe_minutes=h1,
                max_hold_bars=48,
            ),
        },
        {
            "name": "h1_rsi_trend_long",
            "hypothesis": "1h RSI trend long",
            "config": _cfg(
                "prod_majors_h1_rsi_trend_long_v1",
                "rsi_trend_long",
                timeframe_minutes=h1,
                max_hold_bars=48,
            ),
        },
        {
            "name": "h1_bb_mean_revert_short",
            "hypothesis": "1h BB mean-revert short",
            "config": _cfg(
                "prod_majors_h1_bb_mean_revert_short_v1",
                "bb_mean_revert_short",
                timeframe_minutes=h1,
                max_hold_bars=24,
                stop_atr=2.0,
                take_profit_atr=1.5,
            ),
        },
        {
            "name": "h1_bb_mean_revert_long",
            "hypothesis": "1h BB mean-revert long",
            "config": _cfg(
                "prod_majors_h1_bb_mean_revert_long_v1",
                "bb_mean_revert_long",
                timeframe_minutes=h1,
                max_hold_bars=24,
                stop_atr=2.0,
                take_profit_atr=1.5,
            ),
        },
        {
            "name": "h1_vol_donchian_long",
            "hypothesis": "1h vol-expanded donchian long",
            "config": _cfg(
                "prod_majors_h1_vol_donchian_long_v1",
                "vol_donchian_long",
                timeframe_minutes=h1,
                max_hold_bars=48,
                donchian_lookback=24,
            ),
        },
        # --- native 4h ---
        {
            "name": "h4_md_mom_short",
            "hypothesis": "Native 4h multi-day momentum short",
            "config": _cfg(
                "prod_majors_h4_md_mom_short_v1",
                "multi_day_momentum_short",
                timeframe_minutes=h4,
                max_hold_bars=30,  # ~5 days
                donchian_lookback=20,
                htf_slope_bars=6,
            ),
        },
        {
            "name": "h4_md_mom_long",
            "hypothesis": "Native 4h multi-day momentum long",
            "config": _cfg(
                "prod_majors_h4_md_mom_long_v1",
                "multi_day_momentum_long",
                timeframe_minutes=h4,
                max_hold_bars=30,
                donchian_lookback=20,
                htf_slope_bars=6,
            ),
        },
        {
            "name": "h4_dual_md_mom_short",
            "hypothesis": "Native 4h dual-confirm md mom short",
            "config": _cfg(
                "prod_majors_h4_dual_md_mom_short_v1",
                "dual_md_mom_short",
                timeframe_minutes=h4,
                max_hold_bars=30,
                donchian_lookback=20,
                htf_slope_bars=6,
            ),
        },
        {
            "name": "h4_donchian_short",
            "hypothesis": "Native 4h donchian breakdown short",
            "config": _cfg(
                "prod_majors_h4_donchian_short_v1",
                "donchian_short",
                timeframe_minutes=h4,
                max_hold_bars=24,
                donchian_lookback=20,
            ),
        },
        {
            "name": "h4_donchian_long",
            "hypothesis": "Native 4h donchian breakout long",
            "config": _cfg(
                "prod_majors_h4_donchian_long_v1",
                "donchian_breakout",
                timeframe_minutes=h4,
                max_hold_bars=24,
                donchian_lookback=20,
            ),
        },
        {
            "name": "h4_htf_pullback_short",
            "hypothesis": "Native 4h HTF pullback reject short",
            "config": _cfg(
                "prod_majors_h4_htf_pullback_short_v1",
                "htf_pullback_short",
                timeframe_minutes=h4,
                max_hold_bars=24,
                htf_slope_bars=6,
                pullback_lookback=3,
            ),
        },
        {
            "name": "h4_streak_down_short",
            "hypothesis": "Native 4h streak-down short",
            "config": _cfg(
                "prod_majors_h4_streak_down_short_v1",
                "streak_down_days_short",
                timeframe_minutes=h4,
                max_hold_bars=24,
            ),
        },
        {
            "name": "h4_weekly_mom_short",
            "hypothesis": "Native 4h weekly mom short",
            "config": _cfg(
                "prod_majors_h4_weekly_mom_short_v1",
                "weekly_mom_short",
                timeframe_minutes=h4,
                max_hold_bars=42,
            ),
        },
        {
            "name": "h4_slow_ema_cross_short",
            "hypothesis": "Native 4h ema50/200 death cross short",
            "config": _cfg(
                "prod_majors_h4_slow_ema_cross_short_v1",
                "slow_ema_cross_short",
                timeframe_minutes=h4,
                max_hold_bars=42,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
        },
        {
            "name": "h4_slow_ema_cross_long",
            "hypothesis": "Native 4h ema50/200 golden cross long",
            "config": _cfg(
                "prod_majors_h4_slow_ema_cross_long_v1",
                "slow_ema_cross_long",
                timeframe_minutes=h4,
                max_hold_bars=42,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
        },
    ]


def run_majors_research_batch_v6(
    data_dir: Path,
    *,
    max_bars: int | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    catalog = research_catalog_v6()
    market_1h = load_market(
        data_dir,
        60,
        symbols={"BTC-USDT-SWAP", "ETH-USDT-SWAP"},
    )
    market_4h = load_market(
        data_dir,
        240,
        symbols={"BTC-USDT-SWAP", "ETH-USDT-SWAP"},
    )
    if len(market_1h) < 2 and len(market_4h) < 2:
        return {
            "report_type": "majors_research_batch_v6",
            "formal_status": "data_missing",
            "errors": ["need BTC/ETH 1h and/or 4h bars"],
            "places_exchange_orders": False,
            "live_allowed": False,
        }

    rows: list[dict[str, Any]] = []
    for item in catalog:
        cfg: MajorsSleeveConfig = item["config"]
        tf = int(cfg.timeframe_minutes)
        market = market_1h if tf == 60 else market_4h
        if len(market) < 2:
            rows.append(
                {
                    "name": item["name"],
                    "strategy_id": cfg.strategy_id,
                    "signal_family": cfg.signal_family,
                    "timeframe_minutes": tf,
                    "formal_status": "data_missing",
                    "hypothesis": item["hypothesis"],
                    "research_decision": "fail",
                    "reasons": ["market_missing_for_timeframe"],
                    "trades": 0,
                    "return_fraction": None,
                    "profit_factor": None,
                    "max_drawdown_fraction": None,
                    "ending_equity": None,
                }
            )
            continue
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
        summary["timeframe_minutes"] = tf
        summary["timeframe"] = "1h" if tf == 60 else "4h"
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
        "report_type": "majors_research_batch_v6",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "theme": "1h_unused_families_plus_native_4h",
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
                "strategy_id": r.get("strategy_id"),
                "signal_family": r.get("signal_family"),
                "timeframe": r.get("timeframe"),
                "trades": r.get("trades"),
                "return_fraction": r.get("return_fraction"),
                "profit_factor": r.get("profit_factor"),
                "max_drawdown_fraction": r.get("max_drawdown_fraction"),
                "ending_equity": r.get("ending_equity"),
                "research_decision": r.get("research_decision"),
            }
            for r in ranked
        ],
        "results": rows,
        "notes": [
            "Native 1h unused families + dual confirms + native 4h.",
            "No funding filters in v6; no parameter search.",
            "Interesting != paper admission; run multiwindow/OOS next.",
        ],
    }


def write_batch_v6_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
