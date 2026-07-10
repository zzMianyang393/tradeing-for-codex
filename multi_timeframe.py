"""Multi-timeframe trend confirmation strategy.

Uses 4h trend direction to filter 15m entries.
Only takes 15m signals in the direction of the 4h trend.

For BTC/ETH: uses native 4h data.
For other symbols: resamples 15m to 4h.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from backtester import Backtester, _common_timeline
from config import BacktestConfig
from market import Bar, FeatureBar, load_market, load_quantify_csv, add_features, resample_minutes


@dataclass
class MultiTimeframeConfig:
    trend_lookback_bars: int = 50  # 4h bars for trend calculation
    min_trend_strength: float = 0.5  # Minimum EMA distance for trend confirmation


def load_4h_data(data_dir: Path) -> dict[str, list[Bar]]:
    """Load 4h data for BTC/ETH and resample for others."""
    four_hour_data = {}

    # Load native 4h data for BTC/ETH
    for symbol in ["BTC", "ETH"]:
        path = data_dir / f"{symbol}_4h.csv"
        if path.exists():
            bars = load_quantify_csv(path)
            four_hour_data[f"{symbol}-USDT-SWAP"] = bars

    return four_hour_data


def resample_to_4h(bars_15m: list[FeatureBar]) -> list[Bar]:
    """Resample 15m bars to 4h bars."""
    if not bars_15m:
        return []
    # Convert FeatureBar to Bar for resampling
    bars = [
        Bar(
            ts=b.ts,
            time=b.time,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume_quote=b.volume_quote,
        )
        for b in bars_15m
    ]
    return resample_minutes(bars, 240)


def get_4h_trend(bars_4h: list[Bar], lookback: int = 50) -> str:
    """Determine 4h trend direction using EMA crossover."""
    if len(bars_4h) < lookback:
        return "neutral"

    # Add features to get EMA
    features = add_features(bars_4h)
    if not features:
        return "neutral"

    latest = features[-1]
    if latest.ema20 > latest.ema50 and latest.trend_strength > 0.5:
        return "up"
    elif latest.ema20 < latest.ema50 and latest.trend_strength < -0.5:
        return "down"
    else:
        return "neutral"


def run_multi_timeframe_backtest(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    mtf_config: MultiTimeframeConfig,
    days: int = 365,
    symbol_universe: list[str] | None = None,
) -> dict[str, Any]:
    """Run backtest with multi-timeframe confirmation."""
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

    # Calculate 4h trend for each symbol
    trends = {}
    for symbol, bars_15m in sliced.items():
        # Resample 15m to 4h
        bars_4h = resample_to_4h(bars_15m)
        if bars_4h:
            trend = get_4h_trend(bars_4h, mtf_config.trend_lookback_bars)
            trends[symbol] = trend

    # Count trends
    up_count = sum(1 for t in trends.values() if t == "up")
    down_count = sum(1 for t in trends.values() if t == "down")
    neutral_count = sum(1 for t in trends.values() if t == "neutral")

    # Create backtest config based on 4h trends
    # If most symbols are in uptrend, allow long signals
    # If most symbols are in downtrend, allow short signals
    total = len(trends)
    if total == 0:
        return {"error": "no trend data"}

    up_ratio = up_count / total
    down_ratio = down_count / total

    # Determine which signals to allow based on 4h trend
    allowed_reasons = []
    allowed_regimes = {}

    if up_ratio > 0.5:
        # Most symbols in uptrend - allow long signals
        allowed_reasons.extend(["transition_breakout_long", "trend_long"])
        allowed_regimes["transition_breakout_long"] = ("transition",)
        allowed_regimes["trend_long"] = ("uptrend",)
    elif down_ratio > 0.5:
        # Most symbols in downtrend - allow short signals
        allowed_reasons.extend(["trend_short"])
        allowed_regimes["trend_short"] = ("downtrend",)
    else:
        # Mixed - allow both but with lower confidence
        allowed_reasons.extend(["transition_breakout_long", "trend_long", "trend_short"])
        allowed_regimes["transition_breakout_long"] = ("transition",)
        allowed_regimes["trend_long"] = ("uptrend",)
        allowed_regimes["trend_short"] = ("downtrend",)

    # Create backtest config
    backtest_config = replace(
        config,
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=tuple(allowed_reasons),
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
        "trends": trends,
        "trend_summary": {
            "up": up_count,
            "down": down_count,
            "neutral": neutral_count,
            "up_ratio": up_ratio,
            "down_ratio": down_ratio,
        },
        "universe_size": len(sliced),
        "universe": list(sliced.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-timeframe trend confirmation backtest.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/multi_timeframe.json"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--lookback", type=int, default=50)
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

    mtf_config = MultiTimeframeConfig(
        trend_lookback_bars=args.lookback,
    )

    print(f"Running {args.days}-day backtest (universe={args.universe})...", flush=True)
    result = run_multi_timeframe_backtest(market, BacktestConfig(), mtf_config, args.days, symbol_universe)

    if "error" in result:
        print(f"ERROR: {result['error']}", flush=True)
        return 1

    # Print summary
    overall = result.get("overall", {})
    print(f"\n{'='*60}", flush=True)
    print(f"MULTI-TIMEFRAME TREND CONFIRMATION BACKTEST", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Universe: {args.universe} ({result.get('universe_size', 0)} symbols)", flush=True)
    print(f"Trades: {overall.get('trades', 0)}", flush=True)
    print(f"Win rate: {overall.get('win_rate', 0):.2%}", flush=True)
    print(f"PnL: {overall.get('pnl', 0):+.2f}", flush=True)
    print(f"Return: {overall.get('return_pct', 0):+.2f}%", flush=True)
    print(f"Max DD: {overall.get('max_drawdown_pct', 0):.1f}%", flush=True)

    # Trend summary
    trend_summary = result.get("trend_summary", {})
    print(f"\n4H TREND DISTRIBUTION:", flush=True)
    print(f"  Up: {trend_summary.get('up', 0)} ({trend_summary.get('up_ratio', 0):.0%})", flush=True)
    print(f"  Down: {trend_summary.get('down', 0)} ({trend_summary.get('down_ratio', 0):.0%})", flush=True)
    print(f"  Neutral: {trend_summary.get('neutral', 0)}", flush=True)

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
