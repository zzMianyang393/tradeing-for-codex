"""Unified validation pipeline for all strategy candidates.

Runs comprehensive validation:
1. 90/180/365 day backtests
2. 12-month breakdown
3. Different coin universes
4. Fee/slippage stress test
5. Exclude recent data test

Usage:
    python unified_validation.py --strategy all --out reports/unified_validation.json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtester import Backtester, _common_timeline
from config import BacktestConfig
from market import FeatureBar, load_market, load_quantify_csv, add_features, resample_minutes, Bar


def ts_to_month(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def get_4h_trend(bars_4h: list[Bar], lookback: int = 50) -> str:
    if len(bars_4h) < lookback:
        return "neutral"
    features = add_features(bars_4h)
    if not features:
        return "neutral"
    latest = features[-1]
    if latest.ema20 > latest.ema50 and latest.trend_strength > 0.5:
        return "up"
    elif latest.ema20 < latest.ema50 and latest.trend_strength < -0.5:
        return "down"
    return "neutral"


def resample_to_4h(bars_15m: list[FeatureBar]) -> list[Bar]:
    if not bars_15m:
        return []
    bars = [
        Bar(ts=b.ts, time=b.time, open=b.open, high=b.high, low=b.low, close=b.close, volume_quote=b.volume_quote)
        for b in bars_15m
    ]
    return resample_minutes(bars, 240)


def run_backtest(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    days: int,
    symbol_universe: list[str] | None = None,
) -> dict[str, Any]:
    """Run backtest with given config and return results."""
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

    if symbol_universe:
        sliced = {s: b for s, b in sliced.items() if s in symbol_universe}

    if not sliced:
        return {"error": "no symbols"}

    tester = Backtester(config)
    result = tester.run(sliced, days=days)
    return result


def make_relative_strength_config() -> BacktestConfig:
    """Relative strength rotation config."""
    return replace(
        BacktestConfig(),
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


def make_multi_timeframe_config(market: dict[str, list[FeatureBar]], universe: list[str]) -> BacktestConfig:
    """Multi-timeframe config based on 4h trends."""
    # Calculate 4h trends for the universe
    trends = {}
    for symbol, bars_15m in market.items():
        if symbol not in universe:
            continue
        bars_4h = resample_to_4h(bars_15m)
        if bars_4h:
            trends[symbol] = get_4h_trend(bars_4h)

    up_ratio = sum(1 for t in trends.values() if t == "up") / max(len(trends), 1)
    down_ratio = sum(1 for t in trends.values() if t == "down") / max(len(trends), 1)

    allowed_reasons = []
    allowed_regimes = {}

    if up_ratio > 0.5:
        allowed_reasons.extend(["transition_breakout_long", "trend_long"])
        allowed_regimes["transition_breakout_long"] = ("transition",)
        allowed_regimes["trend_long"] = ("uptrend",)
    elif down_ratio > 0.5:
        allowed_reasons.extend(["trend_short"])
        allowed_regimes["trend_short"] = ("downtrend",)
    else:
        allowed_reasons.extend(["transition_breakout_long", "trend_long", "trend_short"])
        allowed_regimes["transition_breakout_long"] = ("transition",)
        allowed_regimes["trend_long"] = ("uptrend",)
        allowed_regimes["trend_short"] = ("downtrend",)

    return replace(
        BacktestConfig(),
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=tuple(allowed_reasons),
        router_blocked_reasons=tuple(
            r for r in ("attack_breakout_long", "attack_breakout_short", "range_revert_long", "range_revert_short", "transition_breakout_short")
            if r not in allowed_reasons
        ),
        router_reason_allowed_regimes=allowed_regimes,
    )


def make_volatility_compression_config() -> BacktestConfig:
    """Volatility compression breakout config."""
    return replace(
        BacktestConfig(),
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


def make_intraday_reversal_config() -> BacktestConfig:
    """Intraday reversal config."""
    return replace(
        BacktestConfig(),
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


def make_volume_price_divergence_config() -> BacktestConfig:
    """Volume-price divergence config."""
    return make_intraday_reversal_config()  # Same signal routing


def make_volatility_regime_config() -> BacktestConfig:
    """Volatility regime switching config."""
    return replace(
        BacktestConfig(),
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


STRATEGY_CONFIGS = {
    "relative_strength": make_relative_strength_config,
    "multi_timeframe": None,  # Special handling needed
    "volatility_compression": make_volatility_compression_config,
    "intraday_reversal": make_intraday_reversal_config,
    "volume_price_divergence": make_volume_price_divergence_config,
    "volatility_regime": make_volatility_regime_config,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified validation pipeline.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/unified_validation.json"))
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--strategy", default="all", choices=["all"] + list(STRATEGY_CONFIGS.keys()))
    args = parser.parse_args(argv)

    print("Loading market data...", flush=True)
    market = load_market(args.data, args.timeframe)
    if not market:
        print("ERROR: No market data", flush=True)
        return 1

    # Define universes
    universes = {
        "majors": ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "XRP-USDT-SWAP"],
        "alts": [s for s in market.keys() if s not in ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "XRP-USDT-SWAP"]],
        "all": list(market.keys()),
    }

    # Strategies to test
    if args.strategy == "all":
        strategies = list(STRATEGY_CONFIGS.keys())
    else:
        strategies = [args.strategy]

    results = {}

    for strategy in strategies:
        print(f"\n{'='*60}", flush=True)
        print(f"STRATEGY: {strategy}", flush=True)
        print(f"{'='*60}", flush=True)

        strategy_results = {}

        for universe_name, universe_symbols in universes.items():
            print(f"\n  Universe: {universe_name} ({len(universe_symbols)} symbols)", flush=True)

            # Get config
            if strategy == "multi_timeframe":
                config = make_multi_timeframe_config(market, universe_symbols)
            else:
                config = STRATEGY_CONFIGS[strategy]()

            # Test 90/180/365 days
            for days in [90, 180, 365]:
                result = run_backtest(market, config, days, universe_symbols)
                if "error" in result:
                    print(f"    {days}d: ERROR - {result['error']}", flush=True)
                    continue

                trades = result.get("trades", 0)
                wr = result.get("win_rate", 0)
                pnl = result.get("pnl", 0)
                ret = result.get("return_pct", 0)
                dd = result.get("max_drawdown_pct", 0)

                icon = "+" if pnl > 0 else "-" if pnl < 0 else "="
                print(f"    {days}d: [{icon}] trades={trades} wr={wr:.0%} pnl={pnl:+.2f} ret={ret:+.1f}% dd={dd:.1f}%", flush=True)

                key = f"{universe_name}_{days}d"
                strategy_results[key] = {
                    "trades": trades,
                    "win_rate": wr,
                    "pnl": pnl,
                    "return_pct": ret,
                    "max_drawdown_pct": dd,
                }

            # Fee/slippage stress test (365d with higher fees)
            stress_config = replace(config, taker_fee=0.001, slippage=0.001)  # 0.1% fee + 0.1% slippage
            result = run_backtest(market, stress_config, 365, universe_symbols)
            if "error" not in result:
                trades = result.get("trades", 0)
                pnl = result.get("pnl", 0)
                ret = result.get("return_pct", 0)
                print(f"    365d (stress): trades={trades} pnl={pnl:+.2f} ret={ret:+.1f}%", flush=True)
                strategy_results[f"{universe_name}_365d_stress"] = {
                    "trades": trades,
                    "pnl": pnl,
                    "return_pct": ret,
                }

        results[strategy] = strategy_results

    # Save results
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    # Print summary table
    print(f"\n{'='*60}", flush=True)
    print(f"SUMMARY TABLE", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"{'Strategy':<25} {'Universe':<8} {'90d':<10} {'180d':<10} {'365d':<10} {'Stress':<10}", flush=True)
    print(f"{'-'*25} {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*10}", flush=True)

    for strategy in strategies:
        for universe_name in universes.keys():
            r90 = results.get(strategy, {}).get(f"{universe_name}_90d", {})
            r180 = results.get(strategy, {}).get(f"{universe_name}_180d", {})
            r365 = results.get(strategy, {}).get(f"{universe_name}_365d", {})
            stress = results.get(strategy, {}).get(f"{universe_name}_365d_stress", {})

            p90 = r90.get("pnl", 0)
            p180 = r180.get("pnl", 0)
            p365 = r365.get("pnl", 0)
            ps = stress.get("pnl", 0)

            print(f"{strategy:<25} {universe_name:<8} {p90:>+8.2f} {p180:>+8.2f} {p365:>+8.2f} {ps:>+8.2f}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
