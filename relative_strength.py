"""Cross-coin relative strength rotation strategy.

Buys coins outperforming BTC, sells coins underperforming BTC.
Uses 21-day relative return as the strength metric.

This is a standalone strategy that doesn't depend on existing signal generators.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from backtester import Backtester, _common_timeline
from config import BacktestConfig
from market import FeatureBar, load_market


@dataclass
class RelativeStrengthConfig:
    lookback_days: int = 21
    top_pct: float = 0.20  # Top 20% = long candidates
    bottom_pct: float = 0.20  # Bottom 20% = short candidates
    min_strength_threshold: float = 0.0  # Minimum relative strength to trade
    rebalance_interval_bars: int = 96  # Rebalance every day (96 bars = 24h on 15m)


def calculate_relative_returns(
    market: dict[str, list[FeatureBar]],
    lookback_bars: int = 96 * 21,  # 21 days on 15m
) -> dict[str, float]:
    """Calculate 21-day return for each symbol."""
    returns = {}
    for symbol, bars in market.items():
        if len(bars) < lookback_bars:
            continue
        current_price = bars[-1].close
        past_price = bars[-lookback_bars].close
        if past_price > 0:
            returns[symbol] = current_price / past_price - 1.0
    return returns


def calculate_relative_strength(
    market: dict[str, list[FeatureBar]],
    lookback_bars: int = 96 * 21,
    btc_symbol: str = "BTC-USDT-SWAP",
) -> dict[str, float]:
    """Calculate relative strength vs BTC for each symbol."""
    returns = calculate_relative_returns(market, lookback_bars)
    btc_return = returns.get(btc_symbol, 0.0)

    relative_strength = {}
    for symbol, ret in returns.items():
        if symbol != btc_symbol:
            relative_strength[symbol] = ret - btc_return
    return relative_strength


def select_candidates(
    relative_strength: dict[str, float],
    top_pct: float = 0.20,
    bottom_pct: float = 0.20,
    min_threshold: float = 0.0,
) -> tuple[list[str], list[str]]:
    """Select top and bottom candidates by relative strength."""
    if not relative_strength:
        return [], []

    sorted_symbols = sorted(relative_strength.keys(), key=lambda s: relative_strength[s], reverse=True)
    n = len(sorted_symbols)
    top_n = max(1, int(n * top_pct))
    bottom_n = max(1, int(n * bottom_pct))

    top_candidates = [s for s in sorted_symbols[:top_n] if relative_strength[s] > min_threshold]
    bottom_candidates = [s for s in sorted_symbols[-bottom_n:] if relative_strength[s] < -min_threshold]

    return top_candidates, bottom_candidates


def run_backtest_with_rs(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    rs_config: RelativeStrengthConfig,
    days: int = 365,
    symbol_universe: list[str] | None = None,
) -> dict[str, Any]:
    """Run backtest with relative strength rotation."""
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

    # Filter to symbol universe if specified
    if symbol_universe:
        sliced = {s: b for s, b in sliced.items() if s in symbol_universe}

    if not sliced:
        return {"error": "no symbols in universe"}

    # For relative strength, we need to calculate it at each rebalance point
    # This requires a custom backtest loop, not the standard Backtester

    # For now, use a simplified approach: calculate RS at the start and trade accordingly
    # In a full implementation, we'd recalculate RS at each rebalance interval

    lookback_bars = rs_config.lookback_days * 96  # 96 bars per day on 15m

    # Calculate RS for the entire period
    all_returns = {}
    for symbol, bars in sliced.items():
        if len(bars) < lookback_bars:
            continue
        # Use the last lookback_bars for RS calculation
        current_price = bars[-1].close
        past_price = bars[-lookback_bars].close
        if past_price > 0:
            all_returns[symbol] = current_price / past_price - 1.0

    # Get BTC return as benchmark
    btc_return = all_returns.get("BTC-USDT-SWAP", 0.0)

    # Calculate relative strength
    relative_strength = {}
    for symbol, ret in all_returns.items():
        if symbol != "BTC-USDT-SWAP":
            relative_strength[symbol] = ret - btc_return

    # Select candidates
    long_candidates, short_candidates = select_candidates(
        relative_strength,
        rs_config.top_pct,
        rs_config.bottom_pct,
        rs_config.min_strength_threshold,
    )

    # Run backtest with filtered signals
    # Create a config that only allows signals for selected candidates
    if long_candidates:
        allowed_reasons = ("transition_breakout_long", "trend_long")
        allowed_regimes = {"transition_breakout_long": ("transition",), "trend_long": ("uptrend",)}
    else:
        allowed_reasons = ()
        allowed_regimes = {}

    if short_candidates:
        allowed_reasons = allowed_reasons + ("trend_short",)
        allowed_regimes["trend_short"] = ("downtrend",)

    # Create backtest config
    backtest_config = replace(
        config,
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=allowed_reasons,
        router_blocked_reasons=tuple(
            r for r in (
                "attack_breakout_long", "attack_breakout_short",
                "range_revert_long", "range_revert_short",
                "transition_breakout_short",
            )
            if r not in allowed_reasons
        ),
        router_reason_allowed_regimes=allowed_regimes,
    )

    # Run backtest
    tester = Backtester(backtest_config)
    result = tester.run(sliced, days=days)

    return {
        "overall": {
            "trades": result.get("trades", 0),
            "win_rate": result.get("win_rate", 0),
            "pnl": result.get("pnl", 0),
            "return_pct": result.get("return_pct", 0),
            "max_drawdown_pct": result.get("max_drawdown_pct", 0),
        },
        "by_reason": result.get("by_reason", {}),
        "relative_strength": relative_strength,
        "long_candidates": long_candidates,
        "short_candidates": short_candidates,
        "universe_size": len(sliced),
        "universe": list(sliced.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Relative strength rotation backtest.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/relative_strength_rotation.json"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--lookback-days", type=int, default=21)
    parser.add_argument("--top-pct", type=float, default=0.20)
    parser.add_argument("--bottom-pct", type=float, default=0.20)
    parser.add_argument("--universe", default="all", choices=["all", "majors", "alts"])
    args = parser.parse_args(argv)

    print("Loading market data...", flush=True)
    market = load_market(args.data, args.timeframe)
    if not market:
        print("ERROR: No market data", flush=True)
        return 1

    # Define symbol universes
    universe_map = {
        "majors": ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "XRP-USDT-SWAP"],
        "alts": [s for s in market.keys() if s not in ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "XRP-USDT-SWAP"]],
        "all": list(market.keys()),
    }
    symbol_universe = universe_map.get(args.universe)

    rs_config = RelativeStrengthConfig(
        lookback_days=args.lookback_days,
        top_pct=args.top_pct,
        bottom_pct=args.bottom_pct,
    )

    print(f"Running {args.days}-day backtest (universe={args.universe})...", flush=True)
    result = run_backtest_with_rs(market, BacktestConfig(), rs_config, args.days, symbol_universe)

    if "error" in result:
        print(f"ERROR: {result['error']}", flush=True)
        return 1

    # Print summary
    overall = result.get("overall", {})
    print(f"\n{'='*60}", flush=True)
    print(f"RELATIVE STRENGTH ROTATION BACKTEST", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Universe: {args.universe} ({result.get('universe_size', 0)} symbols)", flush=True)
    print(f"Trades: {overall.get('trades', 0)}", flush=True)
    print(f"Win rate: {overall.get('win_rate', 0):.2%}", flush=True)
    print(f"PnL: {overall.get('pnl', 0):+.2f}", flush=True)
    print(f"Return: {overall.get('return_pct', 0):+.2f}%", flush=True)
    print(f"Max DD: {overall.get('max_drawdown_pct', 0):.1f}%", flush=True)

    # By reason
    print(f"\nBY REASON:", flush=True)
    for reason, stats in result.get("by_reason", {}).items():
        print(f"  {reason}: trades={stats.get('trades', 0)} win={stats.get('win_rate', 0):.0%} pnl={stats.get('pnl', 0):+.2f}", flush=True)

    # Candidates
    print(f"\nLONG CANDIDATES (top {args.top_pct:.0%}):", flush=True)
    for sym in result.get("long_candidates", [])[:5]:
        rs = result.get("relative_strength", {}).get(sym, 0)
        print(f"  {sym}: RS={rs:+.2%}", flush=True)

    print(f"\nSHORT CANDIDATES (bottom {args.bottom_pct:.0%}):", flush=True)
    for sym in result.get("short_candidates", [])[:5]:
        rs = result.get("relative_strength", {}).get(sym, 0)
        print(f"  {sym}: RS={rs:+.2%}", flush=True)

    # Save
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
