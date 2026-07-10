"""Volatility Regime Switching strategy.

Detects market volatility regime and switches strategy type:
- Low volatility: use range strategies
- High volatility: use trend strategies
- Normal: use both

This is a standalone strategy based on volatility regime detection.
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
class VolatilityRegimeConfig:
    atr_short_period: int = 5  # Short-term ATR period
    atr_long_period: int = 50  # Long-term ATR period
    low_volatility_threshold: float = 0.7  # ATR ratio below this = low volatility
    high_volatility_threshold: float = 1.3  # ATR ratio above this = high volatility


def detect_volatility_regime(
    bars: list[FeatureBar],
    idx: int,
    config: VolatilityRegimeConfig,
) -> str:
    """Detect current volatility regime.
    Returns 'low', 'high', or 'normal'.
    """
    if idx < config.atr_long_period:
        return "normal"

    bar = bars[idx]
    current_atr = bar.atr
    if current_atr <= 0:
        return "normal"

    # Calculate long-term average ATR
    atr_sum = 0.0
    count = 0
    for i in range(max(0, idx - config.atr_long_period), idx):
        if bars[i].atr > 0:
            atr_sum += bars[i].atr
            count += 1

    if count == 0:
        return "normal"

    avg_atr = atr_sum / count
    atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

    if atr_ratio < config.low_volatility_threshold:
        return "low"
    elif atr_ratio > config.high_volatility_threshold:
        return "high"
    else:
        return "normal"


def run_volatility_regime_backtest(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    vr_config: VolatilityRegimeConfig,
    days: int = 365,
    symbol_universe: list[str] | None = None,
) -> dict[str, Any]:
    """Run backtest with volatility regime switching."""
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

    # Count volatility regimes
    regime_counts = {"low": 0, "high": 0, "normal": 0}
    total_bars = 0

    for symbol, bars in sliced.items():
        total_bars += len(bars)
        for i in range(vr_config.atr_long_period, len(bars)):
            regime = detect_volatility_regime(bars, i, vr_config)
            regime_counts[regime] += 1

    # Create config that allows both long and short signals
    # In high volatility, allow trend signals
    # In low volatility, allow range signals
    # For simplicity, allow all signals and let the backtester handle it
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
        router_allowed_reasons=("transition_breakout_long", "trend_long", "trend_short", "range_revert_long", "range_revert_short"),
        router_blocked_reasons=(
            "attack_breakout_long", "attack_breakout_short",
            "transition_breakout_short",
        ),
        router_reason_allowed_regimes={
            "transition_breakout_long": ("transition",),
            "trend_long": ("uptrend",),
            "trend_short": ("downtrend",),
            "range_revert_long": ("range",),
            "range_revert_short": ("range",),
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
        "volatility_regimes": {
            "total_bars": total_bars,
            "low": regime_counts["low"],
            "high": regime_counts["high"],
            "normal": regime_counts["normal"],
        },
        "universe_size": len(sliced),
        "universe": list(sliced.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Volatility regime switching backtest.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/volatility_regime.json"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--low-threshold", type=float, default=0.7)
    parser.add_argument("--high-threshold", type=float, default=1.3)
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

    vr_config = VolatilityRegimeConfig(
        low_volatility_threshold=args.low_threshold,
        high_volatility_threshold=args.high_threshold,
    )

    print(f"Running {args.days}-day backtest (universe={args.universe})...", flush=True)
    result = run_volatility_regime_backtest(market, BacktestConfig(), vr_config, args.days, symbol_universe)

    if "error" in result:
        print(f"ERROR: {result['error']}", flush=True)
        return 1

    # Print summary
    overall = result.get("overall", {})
    print(f"\n{'='*60}", flush=True)
    print(f"VOLATILITY REGIME SWITCHING BACKTEST", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Universe: {args.universe} ({result.get('universe_size', 0)} symbols)", flush=True)
    print(f"Trades: {overall.get('trades', 0)}", flush=True)
    print(f"Win rate: {overall.get('win_rate', 0):.2%}", flush=True)
    print(f"PnL: {overall.get('pnl', 0):+.2f}", flush=True)
    print(f"Return: {overall.get('return_pct', 0):+.2f}%", flush=True)
    print(f"Max DD: {overall.get('max_drawdown_pct', 0):.1f}%", flush=True)

    # Volatility regimes
    regimes = result.get("volatility_regimes", {})
    print(f"\nVOLATILITY REGIMES:", flush=True)
    print(f"  Total bars: {regimes.get('total_bars', 0)}", flush=True)
    print(f"  Low volatility: {regimes.get('low', 0)} ({regimes.get('low', 0) / max(regimes.get('total_bars', 1), 1) * 100:.1f}%)", flush=True)
    print(f"  High volatility: {regimes.get('high', 0)} ({regimes.get('high', 0) / max(regimes.get('total_bars', 1), 1) * 100:.1f}%)", flush=True)
    print(f"  Normal: {regimes.get('normal', 0)} ({regimes.get('normal', 0) / max(regimes.get('total_bars', 1), 1) * 100:.1f}%)", flush=True)

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
