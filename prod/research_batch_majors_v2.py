"""Research batch v2: low-turnover / sparse-event majors candidates.

Builds on v1 infrastructure. Longer holds, daily/4h sampling, slow crosses.
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
    risk_per_trade: float = 0.08,
    max_hold_bars: int = 192,
    stop_atr: float = 2.5,
    take_profit_atr: float = 3.0,
    trailing_atr: float = 2.2,
    max_leverage: float = 3.0,
    max_margin_fraction: float = 0.40,
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


def research_catalog_v2() -> list[dict[str, Any]]:
    """Low-turnover batch — distinct from v1 high-frequency breakouts."""
    return [
        {
            "name": "daily_breakout_long",
            "hypothesis": "UTC-day open: break prior day high in uptrend; hold multi-day",
            "config": _cand(
                "prod_majors_daily_breakout_long_v1",
                "daily_breakout_long",
                max_hold_bars=192,
            ),
        },
        {
            "name": "daily_breakout_short",
            "hypothesis": "UTC-day open: break prior day low in downtrend",
            "config": _cand(
                "prod_majors_daily_breakout_short_v1",
                "daily_breakout_short",
                max_hold_bars=192,
            ),
        },
        {
            "name": "slow_ema_cross_long",
            "hypothesis": "ema50/200 golden cross — sparse trend entry",
            "config": _cand(
                "prod_majors_slow_ema_cross_long_v1",
                "slow_ema_cross_long",
                max_hold_bars=288,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
        },
        {
            "name": "slow_ema_cross_short",
            "hypothesis": "ema50/200 death cross — sparse trend short",
            "config": _cand(
                "prod_majors_slow_ema_cross_short_v1",
                "slow_ema_cross_short",
                max_hold_bars=288,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
        },
        {
            "name": "atr_squeeze_breakout_long",
            "hypothesis": "Volatility compression then breakout long",
            "config": _cand(
                "prod_majors_atr_squeeze_long_v1",
                "atr_squeeze_breakout_long",
                max_hold_bars=128,
            ),
        },
        {
            "name": "atr_squeeze_breakout_short",
            "hypothesis": "Volatility compression then breakdown short",
            "config": _cand(
                "prod_majors_atr_squeeze_short_v1",
                "atr_squeeze_breakout_short",
                max_hold_bars=128,
            ),
        },
        {
            "name": "multi_day_momentum_long",
            "hypothesis": "Daily bar only: 5d momentum + rising ema50",
            "config": _cand(
                "prod_majors_md_mom_long_v1",
                "multi_day_momentum_long",
                max_hold_bars=288,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
        },
        {
            "name": "multi_day_momentum_short",
            "hypothesis": "Daily bar only: 5d down momentum",
            "config": _cand(
                "prod_majors_md_mom_short_v1",
                "multi_day_momentum_short",
                max_hold_bars=288,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
        },
        {
            "name": "four_h_close_trend_long",
            "hypothesis": "4h close only: trend + break last 4h range high",
            "config": _cand(
                "prod_majors_4h_close_long_v1",
                "four_h_close_trend_long",
                max_hold_bars=96,
            ),
        },
        {
            "name": "four_h_close_trend_short",
            "hypothesis": "4h close only: trend + break last 4h range low",
            "config": _cand(
                "prod_majors_4h_close_short_v1",
                "four_h_close_trend_short",
                max_hold_bars=96,
            ),
        },
    ]


def run_majors_research_batch_v2(
    data_dir: Path,
    *,
    max_bars: int | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    catalog = research_catalog_v2()
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
        "report_type": "majors_research_batch_v2",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "theme": "low_turnover_sparse_event",
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
            "Batch v2: daily/4h/slow-cross/squeeze — lower intended turnover than v1.",
            "Single default rules; no grid search.",
            "Interesting != paper or trading admission.",
        ],
    }


def write_batch_v2_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
