"""Monthly breakdown analysis for router experiment results.

Runs a backtest and splits results by calendar month to identify
which months are profitable and which are dragging performance.

Usage:
    python monthly_breakdown.py --mode conservative --out reports/monthly_breakdown_conservative.json
    python monthly_breakdown.py --mode trend_short_factor --out reports/monthly_breakdown_trend_short.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backtester import Backtester, _common_timeline
from config import BacktestConfig
from market import FeatureBar, load_market


MS_PER_DAY = 24 * 60 * 60 * 1000


def make_conservative_config(base: BacktestConfig) -> BacktestConfig:
    """Conservative: only transition_breakout_long via dynamic router."""
    from dataclasses import replace
    # Use the goal_30d_fullseed_40#7 config as base
    goal_config = replace(
        base,
        risk_per_trade=0.39,
        max_margin_fraction=1.95,
        max_total_margin_fraction=1.65,
        max_positions=2,
        active_symbol_limit=6,
        short_window_symbol_limit=10,
        min_score=2.5,
        range_take_profit_atr=0.55,
        range_stop_atr=2.4,
        range_trailing_atr=1.56,
        transition_long_enabled=True,
        transition_short_enabled=True,
        enable_attack_module=False,
        enable_continuation_module=False,
        enable_micro_momentum_module=False,
        enable_funding_module=False,
        enable_open_interest_module=False,
        rm_max_single_position_pct=0.8,
        rm_max_total_position_pct=0.8,
        rm_min_liquidation_distance_pct=0.015,
        max_trade_loss_pct_equity=8.0,
    )
    # Add dynamic router for conservative mode
    return replace(
        goal_config,
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=("transition_breakout_long",),
        router_blocked_reasons=(
            "attack_breakout_long", "attack_breakout_short",
            "range_revert_long", "range_revert_short",
            "transition_breakout_short", "trend_long", "trend_short",
        ),
        router_reason_allowed_regimes={
            "transition_breakout_long": ("transition",),
        },
    )


def make_trend_short_factor_config(base: BacktestConfig) -> BacktestConfig:
    """trend_short_factor: transition_breakout_long + factor-gated trend_short."""
    from dataclasses import replace
    return replace(
        base,
        transition_long_enabled=True,
        transition_short_enabled=False,
        enable_attack_module=False,
        enable_continuation_module=False,
        enable_micro_momentum_module=False,
        enable_funding_module=False,
        enable_open_interest_module=False,
        enable_trade_flow_module=False,
        enable_order_book_module=False,
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=("transition_breakout_long", "trend_short"),
        router_blocked_reasons=(
            "attack_breakout_long", "attack_breakout_short",
            "range_revert_long", "range_revert_short",
            "transition_breakout_short", "trend_long",
        ),
        router_trend_short_factor_gate_enabled=True,
        reason_allowed_regimes={
            "transition_breakout_long": ("transition",),
            "trend_short": ("downtrend",),
        },
        reason_risk_multipliers={"trend_short": 0.35},
    )


def ts_to_month(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def run_monthly_breakdown(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    days: int = 365,
) -> dict:
    """Run backtest and break down results by calendar month."""
    timeline = _common_timeline(market, min_count_fraction=0.50)
    if not timeline:
        return {"error": "no timeline"}

    # Slice market for 365 days
    end_ts = timeline[-1]
    start_ts = end_ts - days * MS_PER_DAY
    sliced = {
        symbol: [bar for bar in bars if start_ts <= bar.ts <= end_ts]
        for symbol, bars in market.items()
    }
    sliced = {s: b for s, b in sliced.items() if b}

    tester = Backtester(config)
    result = tester.run(sliced, days=days)

    # Now we need to re-run with trade tracking to get per-trade timestamps
    # The result already has by_reason breakdown, but we need monthly splits
    # We'll run again with detailed trade logging

    # For monthly breakdown, we need to run the backtester and capture individual trades
    # Let's use a simpler approach: run 12 separate monthly backtests
    monthly_results = {}

    for month_offset in range(12):
        month_end = end_ts - month_offset * 30 * MS_PER_DAY
        month_start = month_end - 30 * MS_PER_DAY

        month_market = {
            symbol: [bar for bar in bars if month_start <= bar.ts <= month_end]
            for symbol, bars in market.items()
        }
        month_market = {s: b for s, b in month_market.items() if len(b) > 100}

        if not month_market:
            continue

        month_label = ts_to_month(month_end)
        try:
            month_tester = Backtester(config)
            month_result = month_tester.run(month_market, days=30)
            monthly_results[month_label] = {
                "trades": month_result.get("trades", 0),
                "pnl": round(month_result.get("pnl", 0), 4),
                "win_rate": round(month_result.get("win_rate", 0), 4),
                "max_drawdown_pct": round(month_result.get("max_drawdown_pct", 0), 4),
                "by_reason": month_result.get("by_reason", {}),
            }
        except Exception as exc:
            monthly_results[month_label] = {"error": str(exc)}

    # Overall result
    overall = {
        "days": days,
        "start_equity": config.start_equity,
        "end_equity": result.get("end_equity", 0),
        "pnl": round(result.get("pnl", 0), 4),
        "return_pct": round(result.get("return_pct", 0), 4),
        "max_drawdown_pct": round(result.get("max_drawdown_pct", 0), 4),
        "trades": result.get("trades", 0),
        "win_rate": round(result.get("win_rate", 0), 4),
        "by_reason": result.get("by_reason", {}),
    }

    # Monthly summary
    profitable_months = sum(1 for m in monthly_results.values() if m.get("pnl", 0) > 0)
    losing_months = sum(1 for m in monthly_results.values() if m.get("pnl", 0) < 0)
    total_months = len(monthly_results)

    # Find drag months (biggest losers)
    drag_months = sorted(
        [(k, v.get("pnl", 0)) for k, v in monthly_results.items() if v.get("pnl", 0) < 0],
        key=lambda x: x[1]
    )[:3]

    # Find best months
    best_months = sorted(
        [(k, v.get("pnl", 0)) for k, v in monthly_results.items() if v.get("pnl", 0) > 0],
        key=lambda x: x[1],
        reverse=True
    )[:3]

    return {
        "overall": overall,
        "monthly": monthly_results,
        "summary": {
            "total_months": total_months,
            "profitable_months": profitable_months,
            "losing_months": losing_months,
            "profit_rate": round(profitable_months / total_months, 4) if total_months > 0 else 0,
            "drag_months": drag_months,
            "best_months": best_months,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monthly breakdown analysis.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/monthly_breakdown.json"))
    parser.add_argument("--mode", default="conservative", choices=["conservative", "trend_short_factor"])
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    args = parser.parse_args(argv)

    print(f"Loading market data...", flush=True)
    market = load_market(args.data, args.timeframe)
    if not market:
        print("ERROR: No market data", flush=True)
        return 1

    base_config = BacktestConfig()
    if args.mode == "conservative":
        config = make_conservative_config(base_config)
        print(f"Mode: conservative (transition_breakout_long only)", flush=True)
    else:
        config = make_trend_short_factor_config(base_config)
        print(f"Mode: trend_short_factor", flush=True)

    print(f"Running {args.days}-day backtest with monthly breakdown...", flush=True)
    result = run_monthly_breakdown(market, config, args.days)

    # Print summary
    overall = result.get("overall", {})
    summary = result.get("summary", {})

    print(f"\n{'='*60}", flush=True)
    print(f"OVERALL: {overall.get('return_pct', 0):+.2f}% | "
          f"trades={overall.get('trades', 0)} | "
          f"win={overall.get('win_rate', 0):.0%} | "
          f"dd={overall.get('max_drawdown_pct', 0):.1f}%",
          flush=True)
    print(f"{'='*60}", flush=True)

    print(f"\nMONTHLY BREAKDOWN:", flush=True)
    monthly = result.get("monthly", {})
    for month in sorted(monthly.keys()):
        m = monthly[month]
        if "error" in m:
            print(f"  {month}: ERROR - {m['error']}", flush=True)
            continue
        pnl = m.get("pnl", 0)
        trades = m.get("trades", 0)
        wr = m.get("win_rate", 0)
        icon = "+" if pnl > 0 else "-" if pnl < 0 else "="
        print(f"  {month}: [{icon}] pnl={pnl:+.2f} trades={trades} win={wr:.0%}", flush=True)

    print(f"\nSUMMARY:", flush=True)
    print(f"  Profitable months: {summary.get('profitable_months', 0)}/{summary.get('total_months', 0)}", flush=True)
    print(f"  Losing months: {summary.get('losing_months', 0)}/{summary.get('total_months', 0)}", flush=True)

    drag = summary.get("drag_months", [])
    if drag:
        print(f"\n  DRAG MONTHS (biggest losers):", flush=True)
        for month, pnl in drag:
            print(f"    {month}: {pnl:+.2f}", flush=True)

    best = summary.get("best_months", [])
    if best:
        print(f"\n  BEST MONTHS:", flush=True)
        for month, pnl in best:
            print(f"    {month}: {pnl:+.2f}", flush=True)

    # Save
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
