"""Cross-window validation for transition breakout long signals.

Runs the transition-only strategy across multiple historical windows
to check if performance is consistent or only valid in recent data.

Usage:
    python transition_cross_validation.py --out reports/transition_cross_validation.json
    python transition_cross_validation.py --windows 90,180,365 --max-windows 8 --out reports/transition_cross_validation.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from backtester import Backtester, _common_timeline, config_for_window
from config import BacktestConfig
from market import FeatureBar, load_market


MS_PER_DAY = 24 * 60 * 60 * 1000


def make_transition_only_config(base: BacktestConfig, wider_regime: bool = False) -> BacktestConfig:
    """Create a config that only allows transition_breakout_long."""
    overrides = dict(
        transition_long_enabled=True,
        transition_short_enabled=False,
        enable_attack_module=False,
        enable_continuation_module=False,
        enable_micro_momentum_module=False,
        enable_funding_module=False,
        enable_open_interest_module=False,
        enable_trade_flow_module=False,
        enable_order_book_module=False,
    )
    if wider_regime:
        overrides.update(dict(
            regime_uptrend_threshold=1.0,
            regime_downtrend_threshold=-1.0,
            regime_range_strength_max=0.7,
        ))
    return replace(base, **overrides)


def rolling_endpoints(
    timeline: list[int],
    window_days: int,
    stride_days: int,
    max_windows: int,
) -> list[int]:
    """Generate rolling window endpoints from latest backwards."""
    if not timeline:
        return []
    first = timeline[0]
    latest = timeline[-1]
    min_end = first + window_days * MS_PER_DAY
    endpoints: list[int] = []
    current = latest
    while current >= min_end and len(endpoints) < max_windows:
        endpoints.append(current)
        current -= stride_days * MS_PER_DAY
    return sorted(endpoints)


def slice_market(
    market: dict[str, list[FeatureBar]],
    end_ts: int,
    window_days: int,
    warmup_days: int,
) -> dict[str, list[FeatureBar]]:
    """Slice market data for a specific window."""
    start_ts = end_ts - (window_days + warmup_days) * MS_PER_DAY
    sliced = {
        symbol: [bar for bar in bars if start_ts <= bar.ts <= end_ts]
        for symbol, bars in market.items()
    }
    return {s: b for s, b in sliced.items() if b}


def run_window(
    market: dict[str, list[FeatureBar]],
    config: BacktestConfig,
    end_ts: int,
    window_days: int,
    warmup_days: int = 45,
) -> dict | None:
    """Run backtest on a single window."""
    sliced = slice_market(market, end_ts, window_days, warmup_days)
    if not sliced:
        return None
    try:
        tester = Backtester(config)
        result = tester.run(sliced, days=window_days)
        result["window_end_ts"] = end_ts
        result["window_days"] = window_days
        return result
    except Exception as exc:
        return {"error": str(exc), "window_end_ts": end_ts, "window_days": window_days}


def format_ts(ts_ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-window validation for transition breakout signals.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/transition_cross_validation.json"))
    parser.add_argument("--windows", default="90,180,365", help="Comma-separated window sizes in days")
    parser.add_argument("--max-windows", type=int, default=8, help="Max windows per size")
    parser.add_argument("--stride-days", type=int, default=30, help="Stride between windows")
    parser.add_argument("--warmup-days", type=int, default=45, help="Warmup period before each window")
    parser.add_argument("--timeframe", type=int, default=15, help="Timeframe in minutes")
    parser.add_argument("--wider-regime", action="store_true", help="Use wider transition band (0.7-1.0)")
    args = parser.parse_args(argv)

    window_sizes = [int(w.strip()) for w in args.windows.split(",")]

    print(f"Loading market data from {args.data}...", flush=True)
    market = load_market(args.data, args.timeframe)
    if not market:
        print("ERROR: No market data found", file=sys.stderr)
        return 1

    timeline = _common_timeline(market, min_count_fraction=0.50)
    if not timeline:
        print("ERROR: No timeline", file=sys.stderr)
        return 1

    print(f"Timeline: {format_ts(timeline[0])} to {format_ts(timeline[-1])} ({len(timeline)} bars)", flush=True)

    # Use a base config and make it transition-only
    base_config = BacktestConfig()
    transition_config = make_transition_only_config(base_config, wider_regime=args.wider_regime)
    if args.wider_regime:
        print("Using wider transition band (0.7-1.0)", flush=True)

    all_results: dict[str, list[dict]] = {}

    for window_days in window_sizes:
        print(f"\n--- Window: {window_days}d ---", flush=True)
        endpoints = rolling_endpoints(timeline, window_days, args.stride_days, args.max_windows)
        print(f"  Endpoints: {len(endpoints)} windows", flush=True)

        window_results: list[dict] = []
        for end_ts in endpoints:
            result = run_window(market, transition_config, end_ts, window_days, args.warmup_days)
            if result is None:
                print(f"  {format_ts(end_ts)}: SKIP (no data)", flush=True)
                continue
            if "error" in result:
                print(f"  {format_ts(end_ts)}: ERROR - {result['error']}", flush=True)
                continue

            trades = result.get("trades", 0)
            pnl = result.get("pnl", 0)
            win_rate = result.get("win_rate", 0)
            dd = result.get("max_drawdown_pct", 0)
            print(f"  {format_ts(end_ts)}: trades={trades} pnl={pnl:+.2f} win={win_rate:.0%} dd={dd:.1f}%", flush=True)
            window_results.append(result)

        # Summarize
        if window_results:
            pnls = [r.get("pnl", 0) for r in window_results]
            trades_list = [r.get("trades", 0) for r in window_results]
            profitable = sum(1 for p in pnls if p > 0)
            total_trades = sum(trades_list)
            median_pnl = sorted(pnls)[len(pnls) // 2] if pnls else 0
            worst_pnl = min(pnls) if pnls else 0
            best_pnl = max(pnls) if pnls else 0

            summary = {
                "window_days": window_days,
                "windows_tested": len(window_results),
                "profitable": profitable,
                "profit_rate": round(profitable / len(window_results), 4) if window_results else 0,
                "total_trades": total_trades,
                "avg_trades_per_window": round(total_trades / len(window_results), 1) if window_results else 0,
                "median_pnl": round(median_pnl, 4),
                "worst_pnl": round(worst_pnl, 4),
                "best_pnl": round(best_pnl, 4),
                "results": window_results,
            }
            all_results[str(window_days)] = summary

            print(f"\n  Summary: {profitable}/{len(window_results)} profitable "
                  f"(profit_rate={summary['profit_rate']:.0%}), "
                  f"total_trades={total_trades}, "
                  f"median_pnl={median_pnl:+.2f}, worst={worst_pnl:+.2f}, best={best_pnl:+.2f}",
                  flush=True)
        else:
            all_results[str(window_days)] = {
                "window_days": window_days,
                "windows_tested": 0,
                "profitable": 0,
                "profit_rate": 0,
                "total_trades": 0,
                "results": [],
            }

    # Final verdict
    print("\n" + "=" * 60, flush=True)
    print("CROSS-VALIDATION VERDICT", flush=True)
    print("=" * 60, flush=True)

    for window_days in window_sizes:
        key = str(window_days)
        if key not in all_results:
            continue
        s = all_results[key]
        status = "PASS" if s["profit_rate"] >= 0.6 else "FAIL"
        print(f"  {window_days}d: {status} | "
              f"profit_rate={s['profit_rate']:.0%} | "
              f"trades={s['total_trades']} | "
              f"median_pnl={s.get('median_pnl', 0):+.2f} | "
              f"worst={s.get('worst_pnl', 0):+.2f}",
              flush=True)

    # Save report
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(all_results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
