from __future__ import annotations

import json
import argparse
from dataclasses import replace
from pathlib import Path

from backtester import Backtester, _common_timeline, config_for_window
from config import BacktestConfig
from market import FeatureBar, discover_symbols, load_market


MS_PER_DAY = 24 * 60 * 60 * 1000


def rolling_endpoints(timeline: list[int], window_days: int, stride_days: int, max_windows: int) -> list[int]:
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


def slice_market_for_endpoint(
    market: dict[str, list[FeatureBar]],
    end_ts: int,
    window_days: int,
    warmup_days: int,
) -> dict[str, list[FeatureBar]]:
    start_ts = end_ts - (window_days + warmup_days) * MS_PER_DAY
    sliced = {
        symbol: [bar for bar in bars if start_ts <= bar.ts <= end_ts]
        for symbol, bars in market.items()
    }
    return {symbol: bars for symbol, bars in sliced.items() if bars}


def summarize_results(results: list[dict]) -> dict:
    available = [item for item in results if item.get("available")]
    if not available:
        return {
            "windows": len(results),
            "available": 0,
            "profitable": 0,
            "profit_rate": 0.0,
            "median_return_pct": 0.0,
            "worst_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }
    returns = sorted(float(item["return_pct"]) for item in available)
    mid = len(returns) // 2
    median = returns[mid] if len(returns) % 2 else (returns[mid - 1] + returns[mid]) / 2.0
    profitable = sum(1 for item in available if float(item["pnl"]) > 0)
    return {
        "windows": len(results),
        "available": len(available),
        "profitable": profitable,
        "profit_rate": round(profitable / len(available), 4),
        "median_return_pct": round(median, 4),
        "worst_return_pct": round(min(returns), 4),
        "max_drawdown_pct": round(max(float(item["max_drawdown_pct"]) for item in available), 4),
    }


def window_config_for_audit(config: BacktestConfig, days: int, symbols: tuple[str, ...]) -> BacktestConfig:
    return config_for_window(config, days, symbols)


def load_market_for_audit(data_dir: Path, config: BacktestConfig) -> dict[str, list[FeatureBar]]:
    include_order_book = (
        config.rm_max_order_book_spread_pct > 0
        or config.rm_min_order_book_depth_quote > 0
    )
    return load_market(
        data_dir,
        config.timeframe_minutes,
        include_funding=config.enable_funding_module,
        include_open_interest=config.enable_open_interest_module,
        include_trade_flow=config.enable_trade_flow_module,
        include_order_book=include_order_book,
    )


def data_source_coverage(data_dir: Path) -> dict:
    symbols = discover_symbols(data_dir)
    sources = {
        "funding": "_funding.csv",
        "open_interest": "_open_interest.csv",
        "trade_flow": "_trades.csv",
        "order_book": "_order_book.csv",
    }
    coverage: dict = {"symbols": len(symbols), "symbol_list": symbols}
    for name, suffix in sources.items():
        available = [symbol for symbol in symbols if (data_dir / f"{symbol}{suffix}").exists()]
        coverage[name] = {
            "files": len(available),
            "coverage": round(len(available) / len(symbols), 4) if symbols else 0.0,
            "symbols": available,
        }
    return coverage


def run_rolling_audit(
    data_dir: Path,
    config: BacktestConfig,
    windows_days: tuple[int, ...] = (180, 90, 60, 30, 14, 7),
    stride_days: int = 14,
    max_windows: int = 12,
    warmup_days: int = 45,
) -> dict:
    market = load_market_for_audit(data_dir, config)
    timeline = _common_timeline(market, min_count_fraction=0.50)
    report: dict = {
        "data_dir": str(data_dir),
        "stride_days": stride_days,
        "max_windows": max_windows,
        "warmup_days": warmup_days,
        "data_source_coverage": data_source_coverage(data_dir),
        "windows": {},
    }
    audit_config = replace(config, enable_long_window_aggressive_profile=False)
    symbols = tuple(sorted(market))
    for days in windows_days:
        tester = Backtester(window_config_for_audit(audit_config, days, symbols))
        entries = []
        for end_ts in rolling_endpoints(timeline, days, stride_days, max_windows):
            window_market = slice_market_for_endpoint(market, end_ts, days, warmup_days)
            result = tester.run(window_market, days=days)
            if result.get("available"):
                result = {
                    key: result[key]
                    for key in (
                        "available",
                        "days",
                        "from",
                        "to",
                        "end_equity",
                        "pnl",
                        "return_pct",
                        "max_drawdown_pct",
                        "trades",
                        "win_rate",
                        "target_pass",
                    )
                }
            entries.append(result)
        report["windows"][str(days)] = {
            "summary": summarize_results(entries),
            "runs": entries,
        }
    return report


def print_report(report: dict) -> None:
    print(f"data={report['data_dir']}", flush=True)
    print(f"stride_days={report['stride_days']} max_windows={report['max_windows']}", flush=True)
    for days, payload in report["windows"].items():
        summary = payload["summary"]
        print(
            f"{days:>3}d windows={summary['available']}/{summary['windows']} "
            f"profitable={summary['profitable']} rate={summary['profit_rate'] * 100:>5.1f}% "
            f"median_ret={summary['median_return_pct']:>7.2f}% "
            f"worst_ret={summary['worst_return_pct']:>7.2f}% "
            f"max_dd={summary['max_drawdown_pct']:>6.2f}%",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rolling-window backtest audits.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/rolling_window_audit.json"))
    parser.add_argument(
        "--module",
        choices=("default", "funding", "open-interest", "trade-flow", "order-book"),
        default="default",
        help="Enable one optional data-source module for isolated rolling validation.",
    )
    parser.add_argument("--stride-days", type=int, default=14)
    parser.add_argument("--max-windows", type=int, default=12)
    parser.add_argument("--warmup-days", type=int, default=45)
    args = parser.parse_args()

    config = BacktestConfig()
    if args.module == "funding":
        config = replace(config, enable_funding_module=True)
    elif args.module == "open-interest":
        config = replace(config, enable_open_interest_module=True)
    elif args.module == "trade-flow":
        config = replace(config, enable_trade_flow_module=True)
    elif args.module == "order-book":
        config = replace(
            config,
            rm_max_order_book_spread_pct=0.002,
            rm_min_order_book_depth_quote=100_000.0,
        )

    report = run_rolling_audit(
        args.data,
        config,
        stride_days=args.stride_days,
        max_windows=args.max_windows,
        warmup_days=args.warmup_days,
    )
    report["module"] = args.module
    report_path = args.out
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print_report(report)
    print(f"report={report_path}", flush=True)


if __name__ == "__main__":
    main()
