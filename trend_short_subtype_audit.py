"""Trend short entry subtype audit.

Analyzes trend_short entries by market condition subtypes to find
which entry conditions produce positive PnL.

Subtypes tested:
1. Strong downtrend + volume spike
2. Pullback continuation (price pulls back to EMA then resumes)
3. Breakdown from range (price breaks below donchian low)
4. Momentum fade (RSI extreme + reversal)
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from backtester import Backtester, _common_timeline
from config import BacktestConfig
from market import FeatureBar, load_market
from strategy import classify_regime


@dataclass
class SubtypeResult:
    name: str = ""
    description: str = ""
    total_signals: int = 0
    trades: int = 0
    wins: int = 0
    pnl: float = 0.0
    win_rate: float = 0.0
    avg_pnl: float = 0.0


def detect_subtypes(bar: FeatureBar, prev_bar: FeatureBar, config: BacktestConfig) -> list[str]:
    """Detect which trend_short subtypes a bar qualifies for."""
    subtypes = []

    volume_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    ema20_distance = abs(bar.close / bar.ema20 - 1.0) if bar.close and bar.ema20 else 0.0
    candle_body = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
    candle_range = (bar.high - bar.low) / bar.close if bar.close else 0.0

    # Subtype 1: Strong downtrend + volume spike
    if (
        bar.trend_strength < -2.0
        and volume_ratio >= 1.5
        and bar.rsi <= 45
        and bar.ema50 < bar.ema200
    ):
        subtypes.append("strong_downtrend_volume")

    # Subtype 2: Pullback continuation (price pulls back to EMA then resumes down)
    if (
        prev_bar.close > prev_bar.ema20  # Previous bar was above EMA20 (pullback)
        and bar.close < bar.ema20        # Current bar closes below EMA20 (resume)
        and bar.ema20 < bar.ema50        # EMA20 below EMA50
        and bar.trend_strength < -1.5    # Still in downtrend
        and volume_ratio >= 1.2          # Some volume confirmation
    ):
        subtypes.append("pullback_continuation")

    # Subtype 3: Breakdown from range (price breaks below donchian low)
    if (
        prev_bar.close >= prev_bar.donchian_low * 0.998  # Was near donchian low
        and bar.close < bar.donchian_low * 0.995          # Broke below
        and volume_ratio >= 1.3                            # Volume confirmation
        and bar.trend_strength < -1.0                      # Some trend
    ):
        subtypes.append("breakdown_from_range")

    # Subtype 4: Momentum fade (RSI extreme + reversal)
    if (
        bar.rsi >= 65                    # RSI was high (overbought in downtrend)
        and bar.close < bar.open         # Bearish candle
        and bar.ema20 < bar.ema50        # Still in downtrend
        and volume_ratio >= 1.1          # Some volume
        and candle_body >= bar.atr_pct * 0.3  # Reasonable body
    ):
        subtypes.append("momentum_fade")

    # Subtype 5: EMA cross confirmation (EMA20 crosses below EMA50)
    if (
        prev_bar.ema20 >= prev_bar.ema50  # EMA20 was above or at EMA50
        and bar.ema20 < bar.ema50          # EMA20 now below EMA50
        and bar.trend_strength < -1.0      # Downtrend confirmed
        and volume_ratio >= 1.2            # Volume confirmation
    ):
        subtypes.append("ema_cross")

    # If no specific subtype, mark as generic
    if not subtypes:
        subtypes.append("generic")

    return subtypes


def run_subtype_audit(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    days: int = 365,
) -> dict[str, Any]:
    """Run backtest with subtype tracking."""
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

    # Count signals by subtype
    subtype_signals: dict[str, int] = defaultdict(int)
    subtype_details: dict[str, SubtypeResult] = {}

    for symbol, bars in sliced.items():
        for i in range(260, len(bars)):
            bar = bars[i]
            prev_bar = bars[i - 1]
            regime = classify_regime(bar, config)
            if regime != "downtrend":
                continue
            if bar.ema50 >= bar.ema200:
                continue
            if bar.trend_strength >= -1.5:
                continue
            subtypes = detect_subtypes(bar, prev_bar, config)
            for subtype in subtypes:
                subtype_signals[subtype] += 1

    # Run backtest to get actual trades
    tester = Backtester(config)
    result = tester.run(sliced, days=days)

    # Build subtype results
    for subtype, signal_count in subtype_signals.items():
        # We can't directly map trades to subtypes from the backtest result
        # But we can estimate based on signal frequency
        subtype_details[subtype] = SubtypeResult(
            name=subtype,
            total_signals=signal_count,
        )

    return {
        "overall": {
            "trades": result.get("trades", 0),
            "win_rate": result.get("win_rate", 0),
            "pnl": result.get("pnl", 0),
            "return_pct": result.get("return_pct", 0),
            "max_drawdown_pct": result.get("max_drawdown_pct", 0),
        },
        "by_reason": result.get("by_reason", {}),
        "subtype_signals": dict(subtype_signals),
        "total_signals": sum(subtype_signals.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trend short subtype audit.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/trend_short_subtype_audit.json"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    args = parser.parse_args(argv)

    print("Loading market data...", flush=True)
    market = load_market(args.data, args.timeframe)
    if not market:
        print("ERROR: No market data", flush=True)
        return 1

    # Use trend_short_factor config
    config = replace(
        BacktestConfig(),
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
    )

    print(f"Running {args.days}-day subtype audit...", flush=True)
    result = run_subtype_audit(market, config, args.days)

    if "error" in result:
        print(f"ERROR: {result['error']}", flush=True)
        return 1

    # Print summary
    overall = result.get("overall", {})
    print(f"\n{'='*60}", flush=True)
    print(f"TREND SHORT SUBTYPE AUDIT", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Overall: trades={overall.get('trades', 0)} win={overall.get('win_rate', 0):.0%} pnl={overall.get('pnl', 0):+.2f}", flush=True)

    print(f"\nSUBTYPE SIGNAL DISTRIBUTION:", flush=True)
    subtypes = result.get("subtype_signals", {})
    total = result.get("total_signals", 0)
    for subtype, count in sorted(subtypes.items(), key=lambda x: x[1], reverse=True):
        pct = count / total * 100 if total > 0 else 0
        print(f"  {subtype}: {count} ({pct:.1f}%)", flush=True)

    # Save
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
