"""Batch research: multiple frozen BTC/ETH 10U candidates, one market load.

No parameter search. Negative results are valid progress.
Does not admit paper/trading.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.majors_account_replay import load_majors_market, replay_majors_account
from prod.majors_contract import (
    HTF_PULLBACK_STRATEGY_ID,
    STRATEGY_ID,
    MajorsSleeveConfig,
    htf_pullback_majors_config,
    primary_majors_config,
)
from prod.majors_contract import TRACK_RESEARCH
from prod.policy import DEFAULT_START_EQUITY_USDT


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _candidate(
    strategy_id: str,
    signal_family: str,
    *,
    name: str,
    hypothesis: str,
    risk_per_trade: float = 0.08,
    max_hold_bars: int = 48,
    stop_atr: float = 2.2,
    take_profit_atr: float = 2.2,
    trailing_atr: float = 2.0,
    max_leverage: float = 4.0,
    max_margin_fraction: float = 0.45,
) -> MajorsSleeveConfig:
    return MajorsSleeveConfig(
        strategy_id=strategy_id,
        track=TRACK_RESEARCH,
        start_equity=DEFAULT_START_EQUITY_USDT,
        signal_family=signal_family,
        risk_per_trade=risk_per_trade,
        max_margin_fraction=max_margin_fraction,
        max_leverage=max_leverage,
        stop_atr=stop_atr,
        take_profit_atr=take_profit_atr,
        trailing_atr=trailing_atr,
        max_hold_bars=max_hold_bars,
        ruin_equity=2.0,
        peak_drawdown_halt=0.70,
    )


def research_catalog() -> list[dict[str, Any]]:
    """Pre-registered batch: distinct profit-source families, single defaults each."""
    return [
        {
            "name": "donchian_long_baseline",
            "hypothesis": "Uptrend channel breakout continuation (existing baseline)",
            "config": primary_majors_config(),
            "baseline": True,
        },
        {
            "name": "htf_pullback_long",
            "hypothesis": "HTF uptrend + EMA20 pullback reclaim long",
            "config": htf_pullback_majors_config(),
            "baseline": True,
        },
        {
            "name": "htf_pullback_short",
            "hypothesis": "HTF downtrend + EMA20 bounce reject short",
            "config": _candidate(
                "prod_majors_htf_pullback_short_v1",
                "htf_pullback_short",
                name="htf_pullback_short",
                hypothesis="",
                max_hold_bars=64,
                take_profit_atr=2.5,
            ),
        },
        {
            "name": "donchian_short",
            "hypothesis": "Downtrend channel breakdown short",
            "config": _candidate(
                "prod_majors_donchian_short_v1",
                "donchian_short",
                name="donchian_short",
                hypothesis="",
                max_hold_bars=48,
            ),
        },
        {
            "name": "ema_cross_long",
            "hypothesis": "EMA20/50 golden cross long",
            "config": _candidate(
                "prod_majors_ema_cross_long_v1",
                "ema_cross_long",
                name="ema_cross_long",
                hypothesis="",
                max_hold_bars=96,
                stop_atr=2.5,
                take_profit_atr=3.0,
            ),
        },
        {
            "name": "ema_cross_short",
            "hypothesis": "EMA20/50 death cross short",
            "config": _candidate(
                "prod_majors_ema_cross_short_v1",
                "ema_cross_short",
                name="ema_cross_short",
                hypothesis="",
                max_hold_bars=96,
                stop_atr=2.5,
                take_profit_atr=3.0,
            ),
        },
        {
            "name": "bb_mean_revert_long",
            "hypothesis": "Bollinger lower-band reclaim long (weak trend filter)",
            "config": _candidate(
                "prod_majors_bb_mr_long_v1",
                "bb_mean_revert_long",
                name="bb_mean_revert_long",
                hypothesis="",
                max_hold_bars=32,
                stop_atr=1.8,
                take_profit_atr=1.5,
                risk_per_trade=0.06,
            ),
        },
        {
            "name": "bb_mean_revert_short",
            "hypothesis": "Bollinger upper-band reject short (weak trend filter)",
            "config": _candidate(
                "prod_majors_bb_mr_short_v1",
                "bb_mean_revert_short",
                name="bb_mean_revert_short",
                hypothesis="",
                max_hold_bars=32,
                stop_atr=1.8,
                take_profit_atr=1.5,
                risk_per_trade=0.06,
            ),
        },
        {
            "name": "vol_donchian_long",
            "hypothesis": "Donchian breakout with volume confirmation",
            "config": _candidate(
                "prod_majors_vol_donchian_long_v1",
                "vol_donchian_long",
                name="vol_donchian_long",
                hypothesis="",
                max_hold_bars=48,
            ),
        },
        {
            "name": "rsi_trend_long",
            "hypothesis": "Uptrend + RSI exit oversold",
            "config": _candidate(
                "prod_majors_rsi_trend_long_v1",
                "rsi_trend_long",
                name="rsi_trend_long",
                hypothesis="",
                max_hold_bars=48,
            ),
        },
        {
            "name": "rsi_trend_short",
            "hypothesis": "Downtrend + RSI exit overbought",
            "config": _candidate(
                "prod_majors_rsi_trend_short_v1",
                "rsi_trend_short",
                name="rsi_trend_short",
                hypothesis="",
                max_hold_bars=48,
            ),
        },
    ]


def _compact_account(report: dict[str, Any]) -> dict[str, Any]:
    account = report.get("account") or {}
    start = float(account.get("starting_equity") or 0)
    end = account.get("ending_equity")
    ret = None
    if end is not None and start > 0:
        ret = float(end) / start - 1.0
    return {
        "strategy_id": report.get("strategy_id"),
        "signal_family": None,
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


def _classify(summary: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if summary.get("formal_status") != "ok":
        return "fail", ["replay_not_ok"]
    trades = int(summary.get("trades") or 0)
    ret = summary.get("return_fraction")
    pf = summary.get("profit_factor")
    dd = summary.get("max_drawdown_fraction")
    if trades < 15:
        reasons.append("low_trade_count")
    if ret is not None and float(ret) <= 0:
        reasons.append("non_positive_return")
    if pf is not None and float(pf) < 1.0:
        reasons.append("pf_below_1")
    if dd is not None and float(dd) > 0.55:
        reasons.append("drawdown_above_55pct")
    if not reasons:
        return "interesting_not_admitted", [
            "positive_10u_after_costs_needs_oos_and_paper"
        ]
    if (
        trades >= 20
        and ret is not None
        and float(ret) > -0.20
        and pf is not None
        and float(pf) >= 0.95
    ):
        return "watchlist_weak", reasons
    return "rejected_weak", reasons


def run_majors_research_batch(
    data_dir: Path,
    *,
    max_bars: int | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    catalog = research_catalog()
    # All configs share BTC/ETH 15m universe
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
        summary["baseline"] = bool(item.get("baseline"))
        decision, reasons = _classify(summary)
        summary["research_decision"] = decision
        summary["reasons"] = reasons
        rows.append(summary)

    # Rank by return then PF (research ranking only)
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
        "report_type": "majors_research_batch_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
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
            "Batch of pre-registered single-default rules; no grid search.",
            "Shared one market load for efficiency.",
            "Interesting != admitted to paper or trading.",
            "Rejected weak results are progress — do not retune same shells.",
        ],
    }


def write_batch_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
