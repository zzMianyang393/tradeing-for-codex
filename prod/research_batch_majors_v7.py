"""Research batch v7: structurally different frozen families.

Themes (not retunes of failed donchian/md_mom primary):
- vol-regime gates (high-vol breakout / low-vol mean-revert)
- failed breakout / failed breakdown
- session filters (NY mom / Asia range)
- outside-bar reversals
- relative-strength selection across BTC/ETH
- dual confirms of the new shorts

Clean BTC/ETH only. No parameter search. Not paper admission.
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
    donchian_lookback: int = 55,
    htf_slope_bars: int = 16,
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


def research_catalog_v7() -> list[dict[str, Any]]:
    """Frozen single-default candidates across 15m / 1h / 4h."""
    items: list[dict[str, Any]] = []

    def add(name: str, hyp: str, cfg: MajorsSleeveConfig) -> None:
        items.append({"name": name, "hypothesis": hyp, "config": cfg})

    # --- 15m structural ---
    add(
        "m15_high_vol_donchian_long",
        "15m donchian long only in high ATR% regime",
        _cfg(
            "prod_majors_m15_high_vol_donchian_long_v1",
            "high_vol_donchian_long",
            timeframe_minutes=15,
            max_hold_bars=32,
            donchian_lookback=55,
        ),
    )
    add(
        "m15_high_vol_donchian_short",
        "15m donchian short only in high ATR% regime",
        _cfg(
            "prod_majors_m15_high_vol_donchian_short_v1",
            "high_vol_donchian_short",
            timeframe_minutes=15,
            max_hold_bars=32,
            donchian_lookback=55,
        ),
    )
    add(
        "m15_low_vol_bb_long",
        "15m BB mean-revert long only in low vol",
        _cfg(
            "prod_majors_m15_low_vol_bb_long_v1",
            "low_vol_bb_long",
            timeframe_minutes=15,
            max_hold_bars=24,
            stop_atr=2.0,
            take_profit_atr=1.5,
        ),
    )
    add(
        "m15_low_vol_bb_short",
        "15m BB mean-revert short only in low vol",
        _cfg(
            "prod_majors_m15_low_vol_bb_short_v1",
            "low_vol_bb_short",
            timeframe_minutes=15,
            max_hold_bars=24,
            stop_atr=2.0,
            take_profit_atr=1.5,
        ),
    )
    add(
        "m15_failed_breakout_short",
        "15m failed channel breakout short",
        _cfg(
            "prod_majors_m15_failed_breakout_short_v1",
            "failed_breakout_short",
            timeframe_minutes=15,
            max_hold_bars=24,
            donchian_lookback=55,
        ),
    )
    add(
        "m15_failed_breakdown_long",
        "15m failed channel breakdown long",
        _cfg(
            "prod_majors_m15_failed_breakdown_long_v1",
            "failed_breakdown_long",
            timeframe_minutes=15,
            max_hold_bars=24,
            donchian_lookback=55,
        ),
    )
    add(
        "m15_ny_session_mom_short",
        "15m multi-day mom short only UTC 13-20",
        _cfg(
            "prod_majors_m15_ny_session_mom_short_v1",
            "ny_session_mom_short",
            timeframe_minutes=15,
            max_hold_bars=48,
        ),
    )
    add(
        "m15_ny_session_mom_long",
        "15m multi-day mom long only UTC 13-20",
        _cfg(
            "prod_majors_m15_ny_session_mom_long_v1",
            "ny_session_mom_long",
            timeframe_minutes=15,
            max_hold_bars=48,
        ),
    )
    add(
        "m15_asia_range_short",
        "15m Asia session BB fade short",
        _cfg(
            "prod_majors_m15_asia_range_short_v1",
            "asia_session_range_short",
            timeframe_minutes=15,
            max_hold_bars=24,
            stop_atr=2.0,
            take_profit_atr=1.5,
        ),
    )
    add(
        "m15_asia_range_long",
        "15m Asia session BB fade long",
        _cfg(
            "prod_majors_m15_asia_range_long_v1",
            "asia_session_range_long",
            timeframe_minutes=15,
            max_hold_bars=24,
            stop_atr=2.0,
            take_profit_atr=1.5,
        ),
    )
    add(
        "m15_outside_reversal_short",
        "15m bearish outside-bar reversal short",
        _cfg(
            "prod_majors_m15_outside_reversal_short_v1",
            "outside_reversal_short",
            timeframe_minutes=15,
            max_hold_bars=16,
        ),
    )
    add(
        "m15_outside_reversal_long",
        "15m bullish outside-bar reversal long",
        _cfg(
            "prod_majors_m15_outside_reversal_long_v1",
            "outside_reversal_long",
            timeframe_minutes=15,
            max_hold_bars=16,
        ),
    )
    add(
        "m15_rel_weak_md_mom_short",
        "15m short the weaker of BTC/ETH on md-mom short",
        _cfg(
            "prod_majors_m15_rel_weak_md_mom_short_v1",
            "rel_weak_md_mom_short",
            timeframe_minutes=15,
            max_hold_bars=48,
        ),
    )
    add(
        "m15_rel_strong_md_mom_long",
        "15m long the stronger of BTC/ETH on md-mom long",
        _cfg(
            "prod_majors_m15_rel_strong_md_mom_long_v1",
            "rel_strong_md_mom_long",
            timeframe_minutes=15,
            max_hold_bars=48,
        ),
    )
    add(
        "m15_dual_failed_breakout_short",
        "15m dual-confirm failed breakout short",
        _cfg(
            "prod_majors_m15_dual_failed_breakout_short_v1",
            "dual_failed_breakout_short",
            timeframe_minutes=15,
            max_hold_bars=24,
            donchian_lookback=55,
        ),
    )

    # --- 1h structural ---
    for name, fam, hyp, hold, dlb in [
        (
            "h1_high_vol_donchian_short",
            "high_vol_donchian_short",
            "1h high-vol donchian short",
            48,
            24,
        ),
        (
            "h1_high_vol_donchian_long",
            "high_vol_donchian_long",
            "1h high-vol donchian long",
            48,
            24,
        ),
        (
            "h1_failed_breakout_short",
            "failed_breakout_short",
            "1h failed breakout short",
            36,
            24,
        ),
        (
            "h1_failed_breakdown_long",
            "failed_breakdown_long",
            "1h failed breakdown long",
            36,
            24,
        ),
        (
            "h1_low_vol_bb_short",
            "low_vol_bb_short",
            "1h low-vol BB short",
            24,
            24,
        ),
        (
            "h1_low_vol_bb_long",
            "low_vol_bb_long",
            "1h low-vol BB long",
            24,
            24,
        ),
        (
            "h1_ny_session_mom_short",
            "ny_session_mom_short",
            "1h NY-session md mom short",
            72,
            24,
        ),
        (
            "h1_outside_reversal_short",
            "outside_reversal_short",
            "1h outside reversal short",
            24,
            24,
        ),
        (
            "h1_rel_weak_md_mom_short",
            "rel_weak_md_mom_short",
            "1h relative-weak md mom short",
            72,
            24,
        ),
        (
            "h1_dual_failed_breakout_short",
            "dual_failed_breakout_short",
            "1h dual failed breakout short",
            36,
            24,
        ),
        (
            "h1_dual_high_vol_donchian_short",
            "dual_high_vol_donchian_short",
            "1h dual high-vol donchian short",
            48,
            24,
        ),
        (
            "h1_dual_ny_session_mom_short",
            "dual_ny_session_mom_short",
            "1h dual NY-session mom short",
            72,
            24,
        ),
    ]:
        add(
            name,
            hyp,
            _cfg(
                f"prod_majors_{name}_v1",
                fam,
                timeframe_minutes=60,
                max_hold_bars=hold,
                donchian_lookback=dlb,
                htf_slope_bars=24,
            ),
        )

    # --- 4h structural ---
    for name, fam, hyp, hold, dlb in [
        (
            "h4_high_vol_donchian_short",
            "high_vol_donchian_short",
            "4h high-vol donchian short",
            24,
            20,
        ),
        (
            "h4_failed_breakout_short",
            "failed_breakout_short",
            "4h failed breakout short",
            18,
            20,
        ),
        (
            "h4_failed_breakdown_long",
            "failed_breakdown_long",
            "4h failed breakdown long",
            18,
            20,
        ),
        (
            "h4_low_vol_bb_short",
            "low_vol_bb_short",
            "4h low-vol BB short",
            12,
            20,
        ),
        (
            "h4_outside_reversal_short",
            "outside_reversal_short",
            "4h outside reversal short",
            12,
            20,
        ),
        (
            "h4_rel_weak_md_mom_short",
            "rel_weak_md_mom_short",
            "4h relative-weak md mom short",
            30,
            20,
        ),
        (
            "h4_dual_failed_breakout_short",
            "dual_failed_breakout_short",
            "4h dual failed breakout short",
            18,
            20,
        ),
        # re-check weekly under structural batch label for gate pipeline
        (
            "h4_weekly_mom_short_recheck",
            "weekly_mom_short",
            "4h weekly mom short recheck on clean data",
            42,
            20,
        ),
    ]:
        add(
            name,
            hyp,
            _cfg(
                f"prod_majors_{name}_v1",
                fam,
                timeframe_minutes=240,
                max_hold_bars=hold,
                donchian_lookback=dlb,
                htf_slope_bars=6,
            ),
        )

    return items


def run_majors_research_batch_v7(
    data_dir: Path,
    *,
    max_bars: int | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    catalog = research_catalog_v7()
    markets = {
        15: load_market(
            data_dir, 15, symbols={"BTC-USDT-SWAP", "ETH-USDT-SWAP"}
        ),
        60: load_market(
            data_dir, 60, symbols={"BTC-USDT-SWAP", "ETH-USDT-SWAP"}
        ),
        240: load_market(
            data_dir, 240, symbols={"BTC-USDT-SWAP", "ETH-USDT-SWAP"}
        ),
    }
    if all(len(m) < 2 for m in markets.values()):
        return {
            "report_type": "majors_research_batch_v7",
            "formal_status": "data_missing",
            "errors": ["need BTC/ETH bars on at least one TF"],
            "places_exchange_orders": False,
            "live_allowed": False,
        }

    rows: list[dict[str, Any]] = []
    for item in catalog:
        cfg: MajorsSleeveConfig = item["config"]
        tf = int(cfg.timeframe_minutes)
        market = markets.get(tf) or {}
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
        summary["timeframe"] = {15: "15m", 60: "1h", 240: "4h"}.get(tf, str(tf))
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
        "report_type": "majors_research_batch_v7",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "theme": "structural_regime_session_failed_break_relative",
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
            "Structural families: vol regime, failed break, session, relative, dual.",
            "Not retunes of suspended donchian primary or revoked h1 md_mom.",
            "Interesting != paper admission; multiwindow required.",
        ],
    }


def write_batch_v7_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
