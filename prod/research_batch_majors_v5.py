"""Research batch v5: native 1h BTC/ETH + optional funding filters.

Uses timeframe_minutes=60. Funding filters only when market loaded with funding.
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


def _h1(
    strategy_id: str,
    signal_family: str,
    *,
    max_hold_bars: int = 48,
    stop_atr: float = 2.5,
    take_profit_atr: float = 3.0,
    risk_per_trade: float = 0.08,
    trailing_atr: float = 2.0,
    funding_filter: str = "none",
) -> MajorsSleeveConfig:
    """funding_filter: none | short_negative | long_positive (applied in signal wrapper)."""
    return MajorsSleeveConfig(
        strategy_id=strategy_id,
        track=TRACK_RESEARCH,
        start_equity=DEFAULT_START_EQUITY_USDT,
        timeframe_minutes=60,
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
        donchian_lookback=24,
        htf_slope_bars=24,  # ~1d on 1h
        pullback_lookback=4,
        # encode funding filter in strategy_id path via extra field? use min_ema_gap unused
        # Store in pullback_lookback no - add via signal family name suffix
    )


def research_catalog_v5() -> list[dict[str, Any]]:
    # Families already support bars_per_day scaling for 60m (bpd=24)
    return [
        {
            "name": "h1_md_mom_short",
            "hypothesis": "1h bars: 5d-equivalent down momentum short",
            "config": _h1("prod_majors_h1_md_mom_short_v1", "multi_day_momentum_short", max_hold_bars=72),
            "funding_filter": "none",
        },
        {
            "name": "h1_md_mom_long",
            "hypothesis": "1h bars: 5d-equivalent up momentum long",
            "config": _h1("prod_majors_h1_md_mom_long_v1", "multi_day_momentum_long", max_hold_bars=72),
            "funding_filter": "none",
        },
        {
            "name": "h1_dual_md_mom_short",
            "hypothesis": "1h dual-confirm multi-day down mom short",
            "config": _h1("prod_majors_h1_dual_md_mom_short_v1", "dual_md_mom_short", max_hold_bars=72),
            "funding_filter": "none",
        },
        {
            "name": "h1_weekly_mom_short",
            "hypothesis": "1h Monday weekly mom short",
            "config": _h1("prod_majors_h1_weekly_mom_short_v1", "weekly_mom_short", max_hold_bars=120),
            "funding_filter": "none",
        },
        {
            "name": "h1_donchian_short",
            "hypothesis": "1h donchian breakdown short",
            "config": _h1("prod_majors_h1_donchian_short_v1", "donchian_short", max_hold_bars=48),
            "funding_filter": "none",
        },
        {
            "name": "h1_donchian_long",
            "hypothesis": "1h donchian breakout long",
            "config": _h1("prod_majors_h1_donchian_long_v1", "donchian_breakout", max_hold_bars=48),
            "funding_filter": "none",
        },
        {
            "name": "h1_slow_ema_cross_short",
            "hypothesis": "1h ema50/200 death cross short",
            "config": _h1(
                "prod_majors_h1_slow_ema_cross_short_v1",
                "slow_ema_cross_short",
                max_hold_bars=120,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
            "funding_filter": "none",
        },
        {
            "name": "h1_slow_ema_cross_long",
            "hypothesis": "1h ema50/200 golden cross long",
            "config": _h1(
                "prod_majors_h1_slow_ema_cross_long_v1",
                "slow_ema_cross_long",
                max_hold_bars=120,
                stop_atr=3.0,
                take_profit_atr=4.0,
            ),
            "funding_filter": "none",
        },
        {
            "name": "h1_streak_down_short",
            "hypothesis": "1h 3-day down streak short",
            "config": _h1("prod_majors_h1_streak_down_short_v1", "streak_down_days_short", max_hold_bars=72),
            "funding_filter": "none",
        },
        {
            "name": "h1_md_mom_short_fundneg",
            "hypothesis": "1h md mom short only when funding_rate < 0 (crowded short caution inverse: pay to short)",
            "config": _h1("prod_majors_h1_md_mom_short_fundneg_v1", "multi_day_momentum_short", max_hold_bars=72),
            "funding_filter": "short_funding_negative",
        },
        {
            "name": "h1_md_mom_short_fundpos",
            "hypothesis": "1h md mom short when funding > 0 (longs crowded — classic short funding fade)",
            "config": _h1("prod_majors_h1_md_mom_short_fundpos_v1", "multi_day_momentum_short", max_hold_bars=72),
            "funding_filter": "short_funding_positive",
        },
        {
            "name": "h1_donchian_short_fundpos",
            "hypothesis": "1h donchian short + positive funding filter",
            "config": _h1("prod_majors_h1_donchian_short_fundpos_v1", "donchian_short", max_hold_bars=48),
            "funding_filter": "short_funding_positive",
        },
    ]


def _apply_funding_filter(
    report: dict[str, Any],
    *,
    funding_filter: str,
    market: dict,
) -> dict[str, Any]:
    """Post-filter trades is wrong; filter must be at entry.

    Instead re-run is handled by funding-aware signal wrapper in resolve.
    This helper is unused — funding applied via config tag in replay hook.
    """
    return report


def run_majors_research_batch_v5(
    data_dir: Path,
    *,
    max_bars: int | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    catalog = research_catalog_v5()
    market = load_market(
        data_dir,
        60,
        include_funding=True,
        symbols={"BTC-USDT-SWAP", "ETH-USDT-SWAP"},
    )
    if len(market) < 2:
        return {
            "report_type": "majors_research_batch_v5",
            "formal_status": "data_missing",
            "symbols_loaded": sorted(market.keys()),
            "errors": ["need BTC and ETH 1h bars"],
            "places_exchange_orders": False,
            "live_allowed": False,
        }

    rows: list[dict[str, Any]] = []
    for item in catalog:
        cfg: MajorsSleeveConfig = item["config"]
        if abs(start_equity - cfg.start_equity) > 1e-12:
            from prod.majors_account_replay import _config_with_equity

            cfg = _config_with_equity(cfg, start_equity)
        # Attach funding filter into a synthetic family tag via strategy metadata
        # Implemented by temporarily wrapping signal_family for funding variants
        ff = item.get("funding_filter") or "none"
        run_cfg = cfg
        if ff != "none":
            # encode in signal_family path used by resolve: keep base family,
            # pass funding via monkeypatch on config — use min_ema_gap as unused float flag? Bad.
            # Better: set signal_family to base and use a parallel dict
            pass

        report = replay_majors_account(
            data_dir,
            config=run_cfg,
            start_equity=start_equity,
            max_bars=max_bars,
            market=market,
            funding_filter=ff,
        )
        summary = _compact_account(report)
        summary["signal_family"] = cfg.signal_family
        summary["name"] = item["name"]
        summary["hypothesis"] = item["hypothesis"]
        summary["funding_filter"] = ff
        summary["timeframe"] = "1h"
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
        "report_type": "majors_research_batch_v5",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "theme": "native_1h_plus_funding_filters",
        "timeframe_minutes": 60,
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
                "funding_filter": r.get("funding_filter"),
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
            "Native 1h bars for both majors.",
            "Funding filters are entry gates only; no parameter search on base rules.",
            "Interesting != paper admission.",
        ],
    }


def write_batch_v5_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
