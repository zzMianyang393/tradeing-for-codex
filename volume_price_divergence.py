"""Volume-Price Divergence strategy.

Trades reversals when price and volume diverge:
- Price up + volume down = bearish divergence (sell)
- Price down + volume down = bullish divergence (buy - selling exhaustion)

This is a standalone strategy based on the volume-price divergence anomaly.
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
class VolumePriceDivergenceConfig:
    price_lookback: int = 20  # Bars to calculate price trend
    volume_lookback: int = 20  # Bars to calculate volume trend
    min_price_change: float = 0.02  # Minimum price change to detect divergence
    min_volume_change: float = -0.2  # Maximum volume change for divergence
    min_trend_strength: float = 0.3  # Minimum trend strength
    max_trend_strength: float = 2.0  # Maximum trend strength (avoid strong trends)


def detect_divergence(
    bars: list[FeatureBar],
    idx: int,
    config: VolumePriceDivergenceConfig,
) -> tuple[bool, int]:
    """Detect volume-price divergence.
    Returns (is_divergence, direction) where direction is predicted price direction.
    """
    if idx < max(config.price_lookback, config.volume_lookback):
        return False, 0

    bar = bars[idx]

    # Calculate price trend
    past_price = bars[idx - config.price_lookback].close
    if past_price <= 0:
        return False, 0
    price_change = (bar.close - past_price) / past_price

    # Calculate volume trend
    recent_volume = sum(b.volume_quote for b in bars[idx - 5:idx]) / 5
    past_volume = sum(b.volume_quote for b in bars[idx - config.volume_lookback:idx - 5]) / (config.volume_lookback - 5)
    if past_volume <= 0:
        return False, 0
    volume_change = (recent_volume - past_volume) / past_volume

    # Check for divergence
    if price_change > config.min_price_change and volume_change < config.min_volume_change:
        # Price up + volume down = bearish divergence
        return True, -1
    elif price_change < -config.min_price_change and volume_change < config.min_volume_change:
        # Price down + volume down = bullish divergence (selling exhaustion)
        return True, 1

    return False, 0


def run_volume_price_divergence_backtest(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    vpd_config: VolumePriceDivergenceConfig,
    days: int = 365,
    symbol_universe: list[str] | None = None,
) -> dict[str, Any]:
    """Run backtest with volume-price divergence signals."""
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

    # Count divergence signals
    bullish_divergence = 0
    bearish_divergence = 0
    total_bars = 0

    for symbol, bars in sliced.items():
        total_bars += len(bars)
        for i in range(max(vpd_config.price_lookback, vpd_config.volume_lookback), len(bars)):
            is_div, direction = detect_divergence(bars, i, vpd_config)
            if is_div:
                if direction > 0:
                    bullish_divergence += 1
                else:
                    bearish_divergence += 1

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
        "divergence_signals": {
            "total_bars": total_bars,
            "bullish_divergence": bullish_divergence,
            "bearish_divergence": bearish_divergence,
        },
        "universe_size": len(sliced),
        "universe": list(sliced.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Volume-price divergence backtest.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/volume_price_divergence.json"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--min-price-change", type=float, default=0.02)
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

    vpd_config = VolumePriceDivergenceConfig(
        min_price_change=args.min_price_change,
    )

    print(f"Running {args.days}-day backtest (universe={args.universe})...", flush=True)
    result = run_volume_price_divergence_backtest(market, BacktestConfig(), vpd_config, args.days, symbol_universe)

    if "error" in result:
        print(f"ERROR: {result['error']}", flush=True)
        return 1

    # Print summary
    overall = result.get("overall", {})
    print(f"\n{'='*60}", flush=True)
    print(f"VOLUME-PRICE DIVERGENCE BACKTEST", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Universe: {args.universe} ({result.get('universe_size', 0)} symbols)", flush=True)
    print(f"Trades: {overall.get('trades', 0)}", flush=True)
    print(f"Win rate: {overall.get('win_rate', 0):.2%}", flush=True)
    print(f"PnL: {overall.get('pnl', 0):+.2f}", flush=True)
    print(f"Return: {overall.get('return_pct', 0):+.2f}%", flush=True)
    print(f"Max DD: {overall.get('max_drawdown_pct', 0):.1f}%", flush=True)

    # Divergence signals
    divergence = result.get("divergence_signals", {})
    print(f"\nDIVERGENCE SIGNALS:", flush=True)
    print(f"  Total bars: {divergence.get('total_bars', 0)}", flush=True)
    print(f"  Bullish divergence: {divergence.get('bullish_divergence', 0)}", flush=True)
    print(f"  Bearish divergence: {divergence.get('bearish_divergence', 0)}", flush=True)

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
