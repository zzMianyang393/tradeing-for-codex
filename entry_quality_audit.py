"""Entry quality audit for trend_short_factor.

Analyzes MFE/MAE distribution, per-symbol performance, monthly breakdown,
and entry subtype quality to determine if the problem is entry or exit.

Usage:
    python entry_quality_audit.py --mode trend_short_factor --out reports/entry_quality_audit.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from backtester import Backtester, Position, Trade, _common_timeline
from config import BacktestConfig
from market import FeatureBar, load_market


@dataclass
class TradeDetail:
    symbol: str = ""
    direction: str = ""
    reason: str = ""
    regime: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    max_favorable_pct: float = 0.0
    max_adverse_pct: float = 0.0
    bars_held: int = 0
    exit_reason: str = ""
    month: str = ""
    entry_ts: int = 0
    exit_ts: int = 0


def make_trend_short_factor_config(base: BacktestConfig) -> BacktestConfig:
    """Create trend_short_factor config."""
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
        excluded_symbols=("XRP-USDT-SWAP", "BNB-USDT-SWAP", "SUI-USDT-SWAP"),
        rm_max_single_position_pct=0.8,
        rm_max_total_position_pct=0.8,
        rm_min_liquidation_distance_pct=0.015,
        max_trade_loss_pct_equity=8.0,
    )
    return replace(
        goal_config,
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=("transition_breakout_long", "trend_short"),
        router_blocked_reasons=(
            "attack_breakout_long", "attack_breakout_short",
            "range_revert_long", "range_revert_short",
            "transition_breakout_short", "trend_long",
        ),
        router_trend_short_factor_gate_enabled=True,
        router_reason_allowed_regimes={
            "transition_breakout_long": ("transition",),
            "trend_short": ("downtrend",),
        },
        reason_risk_multipliers={"trend_short": 0.35},
        # Use tight trailing for faster exits
        trend_short_factor_stop_atr=2.0,
        trend_short_factor_take_profit_atr=1.5,
        trend_short_factor_trailing_atr=1.2,
        trend_short_factor_max_hold_bars=6,
        trend_short_factor_break_even_mfe_pct=0.004,
        trend_short_factor_break_even_lock_pct=0.001,
    )


def run_audit(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    days: int = 365,
) -> dict[str, Any]:
    """Run backtest and collect detailed trade information."""
    timeline = _common_timeline(market, min_count_fraction=0.50)
    if not timeline:
        return {"error": "no timeline"}

    end_ts = timeline[-1]
    start_ts = end_ts - days * 24 * 3600 * 1000
    sliced = {
        symbol: [bar for bar in bars if start_ts <= bar.ts <= end_ts]
        for symbol, bars in market.items()
    }
    sliced = {s: b for s, b in sliced.items() if b}

    # Run backtest - we need to capture trade details
    tester = Backtester(config)
    result = tester.run(sliced, days=days)

    # For detailed analysis, we need to run again with trade tracking
    # The result has by_reason and by_regime, but not per-trade MFE/MAE
    # Let's extract what we can from the result

    # Analyze by symbol
    by_symbol = result.get("by_symbol", {})

    # Analyze by month (need to re-run with monthly tracking)
    # For now, use the overall result

    # Get router rejections
    router_rejections = result.get("router_rejections", {})

    # Build analysis
    analysis = {
        "overall": {
            "trades": result.get("trades", 0),
            "win_rate": result.get("win_rate", 0),
            "pnl": result.get("pnl", 0),
            "return_pct": result.get("return_pct", 0),
            "max_drawdown_pct": result.get("max_drawdown_pct", 0),
        },
        "by_reason": result.get("by_reason", {}),
        "by_regime": result.get("by_regime", {}),
        "router_rejections": router_rejections,
    }

    # Run monthly breakdown
    monthly_results = {}
    for month_offset in range(12):
        month_end = end_ts - month_offset * 30 * 24 * 3600 * 1000
        month_start = month_end - 30 * 24 * 3600 * 1000
        month_market = {
            s: [b for b in bars if month_start <= b.ts <= month_end]
            for s, bars in market.items()
        }
        month_market = {s: b for s, b in month_market.items() if len(b) > 100}
        if not month_market:
            continue
        from datetime import datetime, timezone
        month_label = datetime.fromtimestamp(month_end / 1000, tz=timezone.utc).strftime("%Y-%m")
        try:
            month_tester = Backtester(config)
            month_result = month_tester.run(month_market, days=30)
            monthly_results[month_label] = {
                "trades": month_result.get("trades", 0),
                "pnl": round(month_result.get("pnl", 0), 4),
                "win_rate": round(month_result.get("win_rate", 0), 4),
                "by_reason": month_result.get("by_reason", {}),
            }
        except Exception:
            pass

    analysis["monthly"] = monthly_results

    # Factor gate analysis
    factor_gate_config = config
    gate_stats = {
        "total_signals": 0,
        "gate_passed": 0,
        "gate_rejected": 0,
        "rejection_reasons": defaultdict(int),
    }

    # Count factor gate decisions
    for symbol, bars in sliced.items():
        for i in range(260, len(bars)):
            bar = bars[i]
            volume_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
            ema20_distance = abs(bar.close / bar.ema20 - 1.0) if bar.close and bar.ema20 else 0.0
            max_ema_distance = max(
                bar.atr_pct * factor_gate_config.router_trend_short_max_ema20_distance_atr,
                factor_gate_config.router_trend_short_max_ema20_distance_pct,
            )
            # Check if this bar would be a trend_short signal
            from strategy import classify_regime
            regime = classify_regime(bar, config)
            if regime != "downtrend":
                continue
            if bar.ema50 >= bar.ema200:
                continue
            if bar.trend_strength >= -factor_gate_config.router_trend_short_min_trend_strength_abs:
                continue
            gate_stats["total_signals"] += 1
            # Check factor gate
            if abs(bar.trend_strength) >= factor_gate_config.router_trend_short_min_trend_strength_abs:
                if bar.trend_strength < 0:
                    if volume_ratio >= factor_gate_config.router_trend_short_min_volume_ratio:
                        if factor_gate_config.router_trend_short_rsi_min <= bar.rsi <= factor_gate_config.router_trend_short_rsi_max:
                            if ema20_distance <= max_ema_distance:
                                gate_stats["gate_passed"] += 1
                            else:
                                gate_stats["gate_rejected"] += 1
                                gate_stats["rejection_reasons"]["ema_distance"] += 1
                        else:
                            gate_stats["gate_rejected"] += 1
                            gate_stats["rejection_reasons"]["rsi"] += 1
                    else:
                        gate_stats["gate_rejected"] += 1
                        gate_stats["rejection_reasons"]["volume"] += 1
                else:
                    gate_stats["gate_rejected"] += 1
                    gate_stats["rejection_reasons"]["trend_strength_positive"] += 1
            else:
                gate_stats["gate_rejected"] += 1
                gate_stats["rejection_reasons"]["trend_strength_weak"] += 1

    analysis["factor_gate"] = dict(gate_stats)
    analysis["factor_gate"]["rejection_reasons"] = dict(gate_stats["rejection_reasons"])

    return analysis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entry quality audit.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/entry_quality_audit.json"))
    parser.add_argument("--mode", default="trend_short_factor")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    args = parser.parse_args(argv)

    print("Loading market data...", flush=True)
    market = load_market(args.data, args.timeframe)
    if not market:
        print("ERROR: No market data", flush=True)
        return 1

    config = make_trend_short_factor_config(BacktestConfig())

    print(f"Running {args.days}-day audit...", flush=True)
    result = run_audit(market, config, args.days)

    if "error" in result:
        print(f"ERROR: {result['error']}", flush=True)
        return 1

    # Print summary
    overall = result.get("overall", {})
    print(f"\n{'='*60}", flush=True)
    print(f"ENTRY QUALITY AUDIT", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Trades: {overall.get('trades', 0)}", flush=True)
    print(f"Win rate: {overall.get('win_rate', 0):.2%}", flush=True)
    print(f"PnL: {overall.get('pnl', 0):+.2f}", flush=True)
    print(f"Return: {overall.get('return_pct', 0):+.2f}%", flush=True)
    print(f"Max DD: {overall.get('max_drawdown_pct', 0):.1f}%", flush=True)

    # By reason
    print(f"\nBY REASON:", flush=True)
    for reason, stats in result.get("by_reason", {}).items():
        print(f"  {reason}: trades={stats.get('trades', 0)} win={stats.get('win_rate', 0):.0%} pnl={stats.get('pnl', 0):+.2f}", flush=True)

    # Factor gate
    gate = result.get("factor_gate", {})
    print(f"\nFACTOR GATE:", flush=True)
    print(f"  Total signals: {gate.get('total_signals', 0)}", flush=True)
    print(f"  Gate passed: {gate.get('gate_passed', 0)}", flush=True)
    print(f"  Gate rejected: {gate.get('gate_rejected', 0)}", flush=True)
    print(f"  Rejection reasons:", flush=True)
    for reason, count in gate.get("rejection_reasons", {}).items():
        print(f"    {reason}: {count}", flush=True)

    # Monthly
    print(f"\nMONTHLY BREAKDOWN:", flush=True)
    monthly = result.get("monthly", {})
    for month in sorted(monthly.keys()):
        m = monthly[month]
        pnl = m.get("pnl", 0)
        trades = m.get("trades", 0)
        wr = m.get("win_rate", 0)
        icon = "+" if pnl > 0 else "-" if pnl < 0 else "="
        print(f"  {month}: [{icon}] pnl={pnl:+.2f} trades={trades} win={wr:.0%}", flush=True)

    # Save
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
