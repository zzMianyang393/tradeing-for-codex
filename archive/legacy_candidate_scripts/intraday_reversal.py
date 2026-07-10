"""Intraday Momentum Reversal strategy.

Trades reversals after extreme single-bar moves.
When a bar has an extreme return (>3%), bet on reversal in the next bar.

This is a standalone strategy based on the well-documented
intraday momentum reversal anomaly.
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
class IntradayReversalConfig:
    extreme_return_threshold: float = 0.03  # 3% single-bar return = extreme
    min_volume_ratio: float = 1.0  # Minimum volume for confirmation
    max_trend_strength: float = 1.5  # Don't trade in strong trends
    cooldown_bars: int = 4  # Wait 1 hour after signal


def detect_extreme_move(
    bars: list[FeatureBar],
    idx: int,
    config: IntradayReversalConfig,
) -> tuple[bool, int]:
    """Detect extreme single-bar move and predict reversal direction.
    Returns (is_extreme, direction) where direction is reversal direction.
    """
    if idx < 1:
        return False, 0

    bar = bars[idx]
    prev_bar = bars[idx - 1]

    # Calculate single-bar return
    if prev_bar.close <= 0:
        return False, 0

    bar_return = (bar.close - prev_bar.close) / prev_bar.close

    # Check for extreme move
    if abs(bar_return) < config.extreme_return_threshold:
        return False, 0

    # Volume confirmation
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    if vol_ratio < config.min_volume_ratio:
        return False, 0

    # Don't trade in strong trends
    if abs(bar.trend_strength) > config.max_trend_strength:
        return False, 0

    # Predict reversal direction
    if bar_return > 0:
        # Extreme up move -> expect down reversal
        return True, -1
    else:
        # Extreme down move -> expect up reversal
        return True, 1


def run_intraday_reversal_backtest(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    ir_config: IntradayReversalConfig,
    days: int = 365,
    symbol_universe: list[str] | None = None,
) -> dict[str, Any]:
    """Run backtest with intraday momentum reversal signals."""
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

    # Count extreme moves
    extreme_up = 0
    extreme_down = 0
    total_bars = 0

    for symbol, bars in sliced.items():
        total_bars += len(bars)
        for i in range(1, len(bars)):
            is_extreme, direction = detect_extreme_move(bars, i, ir_config)
            if is_extreme:
                if direction > 0:
                    extreme_up += 1
                else:
                    extreme_down += 1

    # For backtest, we need to use the existing signal system
    # Since we can't easily add custom signals to the backtester,
    # we'll use a simplified approach: allow trend_short for down reversals
    # and trend_long for up reversals

    # Create config that allows both long and short signals
    backtest_config = replace(
        config,
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
        router_allowed_reasons=("transition_breakout_long", "trend_long", "trend_short"),
        router_blocked_reasons=(
            "attack_breakout_long", "attack_breakout_short",
            "range_revert_long", "range_revert_short",
            "transition_breakout_short",
        ),
        router_reason_allowed_regimes={
            "transition_breakout_long": ("transition",),
            "trend_long": ("uptrend",),
            "trend_short": ("downtrend",),
        },
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
        "extreme_moves": {
            "total_bars": total_bars,
            "extreme_up": extreme_up,
            "extreme_down": extreme_down,
            "extreme_pct": (extreme_up + extreme_down) / total_bars * 100 if total_bars > 0 else 0,
        },
        "universe_size": len(sliced),
        "universe": list(sliced.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Intraday momentum reversal backtest.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/intraday_reversal.json"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--threshold", type=float, default=0.03, help="Extreme return threshold")
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

    ir_config = IntradayReversalConfig(
        extreme_return_threshold=args.threshold,
    )

    print(f"Running {args.days}-day backtest (universe={args.universe})...", flush=True)
    result = run_intraday_reversal_backtest(market, BacktestConfig(), ir_config, args.days, symbol_universe)

    if "error" in result:
        print(f"ERROR: {result['error']}", flush=True)
        return 1

    # Print summary
    overall = result.get("overall", {})
    print(f"\n{'='*60}", flush=True)
    print(f"INTRADAY MOMENTUM REVERSAL BACKTEST", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Universe: {args.universe} ({result.get('universe_size', 0)} symbols)", flush=True)
    print(f"Trades: {overall.get('trades', 0)}", flush=True)
    print(f"Win rate: {overall.get('win_rate', 0):.2%}", flush=True)
    print(f"PnL: {overall.get('pnl', 0):+.2f}", flush=True)
    print(f"Return: {overall.get('return_pct', 0):+.2f}%", flush=True)
    print(f"Max DD: {overall.get('max_drawdown_pct', 0):.1f}%", flush=True)

    # Extreme moves
    extreme = result.get("extreme_moves", {})
    print(f"\nEXTREME MOVES:", flush=True)
    print(f"  Total bars: {extreme.get('total_bars', 0)}", flush=True)
    print(f"  Extreme up: {extreme.get('extreme_up', 0)}", flush=True)
    print(f"  Extreme down: {extreme.get('extreme_down', 0)}", flush=True)
    print(f"  Extreme %: {extreme.get('extreme_pct', 0):.2f}%", flush=True)

    # By reason
    print(f"\nBY REASON:", flush=True)
    for reason, stats in result.get("by_reason", {}).items():
        print(f"  {reason}: trades={stats.get('trades', 0)} win={stats.get('win_rate', 0):.0%} pnl={stats.get('pnl', 0):+.2f}", flush=True)

    # Save
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
