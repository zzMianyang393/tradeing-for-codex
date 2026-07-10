"""Candidate validation: 12-month breakdown, by_symbol, exclude 2026-05~07.

Validates a strategy candidate against hard elimination criteria.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtester import Backtester, _common_timeline
from config import BacktestConfig
from market import FeatureBar, load_market, load_quantify_csv, add_features, resample_minutes, Bar


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


def run_monthly_backtest(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    end_ts: int,
    days: int = 30,
    symbol_universe: list[str] | None = None,
) -> dict[str, Any]:
    """Run backtest for a single month."""
    MS_PER_DAY = 24 * 3600 * 1000
    start_ts = end_ts - days * MS_PER_DAY
    sliced = {s: [b for b in bars if start_ts <= b.ts <= end_ts] for s, bars in market.items()}
    sliced = {s: b for s, b in sliced.items() if len(b) > 100}
    if symbol_universe:
        sliced = {s: b for s, b in sliced.items() if s in symbol_universe}
    if not sliced:
        return {"error": "no data"}

    # Calculate 4h trends
    trends = {}
    for symbol, bars_15m in sliced.items():
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

    backtest_config = replace(
        config,
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=tuple(allowed_reasons),
        router_blocked_reasons=tuple(
            r for r in ("attack_breakout_long", "attack_breakout_short", "range_revert_long", "range_revert_short", "transition_breakout_short")
            if r not in allowed_reasons
        ),
        router_reason_allowed_regimes=allowed_regimes,
    )

    tester = Backtester(backtest_config)
    result = tester.run(sliced, days=days)
    return result


def ts_to_month(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Candidate validation.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/candidate_validation.json"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--exclude-months", default="2026-05,2026-06,2026-07", help="Comma-separated months to exclude")
    args = parser.parse_args(argv)

    print("Loading market data...", flush=True)
    market = load_market(args.data, args.timeframe)
    if not market:
        print("ERROR: No market data", flush=True)
        return 1

    # Define alts universe
    alts_universe = [s for s in market.keys() if s not in ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "XRP-USDT-SWAP"]]

    timeline = _common_timeline(market, min_count_fraction=0.50)
    if not timeline:
        print("ERROR: No timeline", flush=True)
        return 1

    end_ts = timeline[-1]
    MS_PER_DAY = 24 * 3600 * 1000

    # 1. Run full 365-day backtest
    print(f"\n{'='*60}", flush=True)
    print(f"FULL 365-DAY BACKTEST (alts universe)", flush=True)
    print(f"{'='*60}", flush=True)

    start_ts = end_ts - args.days * MS_PER_DAY
    sliced_full = {s: [b for b in bars if start_ts <= b.ts <= end_ts] for s, bars in market.items()}
    sliced_full = {s: b for s, b in sliced_full.items() if s in alts_universe and len(b) > 100}

    # Calculate trends for full period
    trends_full = {}
    for symbol, bars_15m in sliced_full.items():
        bars_4h = resample_to_4h(bars_15m)
        if bars_4h:
            trends_full[symbol] = get_4h_trend(bars_4h)

    up_ratio = sum(1 for t in trends_full.values() if t == "up") / max(len(trends_full), 1)
    down_ratio = sum(1 for t in trends_full.values() if t == "down") / max(len(trends_full), 1)

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

    full_config = replace(
        BacktestConfig(),
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=tuple(allowed_reasons),
        router_blocked_reasons=tuple(
            r for r in ("attack_breakout_long", "attack_breakout_short", "range_revert_long", "range_revert_short", "transition_breakout_short")
            if r not in allowed_reasons
        ),
        router_reason_allowed_regimes=allowed_regimes,
    )

    tester = Backtester(full_config)
    full_result = tester.run(sliced_full, days=args.days)

    print(f"Trades: {full_result.get('trades', 0)}", flush=True)
    print(f"Win rate: {full_result.get('win_rate', 0):.2%}", flush=True)
    print(f"PnL: {full_result.get('pnl', 0):+.2f}", flush=True)
    print(f"Return: {full_result.get('return_pct', 0):+.2f}%", flush=True)
    print(f"Max DD: {full_result.get('max_drawdown_pct', 0):.1f}%", flush=True)

    # 2. 12-month breakdown
    print(f"\n{'='*60}", flush=True)
    print(f"12-MONTH BREAKDOWN", flush=True)
    print(f"{'='*60}", flush=True)

    monthly_results = {}
    for month_offset in range(12):
        month_end = end_ts - month_offset * 30 * MS_PER_DAY
        month_label = ts_to_month(month_end)
        month_result = run_monthly_backtest(market, BacktestConfig(), month_end, 30, alts_universe)
        if "error" not in month_result:
            monthly_results[month_label] = {
                "trades": month_result.get("trades", 0),
                "pnl": round(month_result.get("pnl", 0), 4),
                "win_rate": round(month_result.get("win_rate", 0), 4),
                "by_reason": month_result.get("by_reason", {}),
            }
            pnl = month_result.get("pnl", 0)
            trades = month_result.get("trades", 0)
            wr = month_result.get("win_rate", 0)
            icon = "+" if pnl > 0 else "-" if pnl < 0 else "="
            print(f"  {month_label}: [{icon}] pnl={pnl:+.2f} trades={trades} win={wr:.0%}", flush=True)

    # 3. by_symbol breakdown
    print(f"\n{'='*60}", flush=True)
    print(f"BY_SYMBOL BREAKDOWN", flush=True)
    print(f"{'='*60}", flush=True)

    by_symbol = full_result.get("by_symbol", {})
    for symbol in sorted(by_symbol.keys()):
        stats = by_symbol[symbol]
        print(f"  {symbol}: trades={stats.get('trades', 0)} win={stats.get('win_rate', 0):.0%} pnl={stats.get('pnl', 0):+.2f}", flush=True)

    # 4. Exclude months test
    exclude_months = [m.strip() for m in args.exclude_months.split(",")]
    print(f"\n{'='*60}", flush=True)
    print(f"EXCLUDING MONTHS: {exclude_months}", flush=True)
    print(f"{'='*60}", flush=True)

    # Run backtest excluding specified months
    excluded_monthly = {k: v for k, v in monthly_results.items() if k not in exclude_months}
    excluded_pnl = sum(v.get("pnl", 0) for v in excluded_monthly.values())
    excluded_trades = sum(v.get("trades", 0) for v in excluded_monthly.values())
    print(f"Excluding {exclude_months}:", flush=True)
    print(f"  Remaining months: {len(excluded_monthly)}", flush=True)
    print(f"  Total PnL: {excluded_pnl:+.2f}", flush=True)
    print(f"  Total trades: {excluded_trades}", flush=True)

    # 5. Hard elimination check
    print(f"\n{'='*60}", flush=True)
    print(f"HARD ELIMINATION CHECK", flush=True)
    print(f"{'='*60}", flush=True)

    elimination_reasons = []
    if full_result.get("return_pct", 0) < 0:
        elimination_reasons.append("365d return negative")
    if full_result.get("max_drawdown_pct", 0) > 45:
        elimination_reasons.append(f"max drawdown {full_result.get('max_drawdown_pct', 0):.1f}% > 45%")
    if full_result.get("trades", 0) < 30:
        elimination_reasons.append(f"too few trades ({full_result.get('trades', 0)})")

    # Check single month contribution
    profitable_months = sum(1 for v in monthly_results.values() if v.get("pnl", 0) > 0)
    if profitable_months < 4:
        elimination_reasons.append(f"only {profitable_months} profitable months")

    if elimination_reasons:
        print(f"STATUS: ELIMINATED", flush=True)
        for reason in elimination_reasons:
            print(f"  - {reason}", flush=True)
    else:
        print(f"STATUS: PASSED (needs further validation)", flush=True)

    # Save
    result = {
        "full_365d": {
            "trades": full_result.get("trades", 0),
            "win_rate": full_result.get("win_rate", 0),
            "pnl": full_result.get("pnl", 0),
            "return_pct": full_result.get("return_pct", 0),
            "max_drawdown_pct": full_result.get("max_drawdown_pct", 0),
        },
        "by_reason": full_result.get("by_reason", {}),
        "by_symbol": by_symbol,
        "monthly": monthly_results,
        "exclude_months": exclude_months,
        "excluded_pnl": excluded_pnl,
        "excluded_trades": excluded_trades,
        "elimination_reasons": elimination_reasons,
        "status": "ELIMINATED" if elimination_reasons else "PASSED",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
