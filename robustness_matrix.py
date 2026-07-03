from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from backtester import run_report
from config import BacktestConfig


def compact_window(result: dict) -> str:
    if not result.get("available"):
        return "NA"
    status = "P" if result.get("target_pass") else "F"
    return (
        f"{status} pnl={result['pnl']:.2f} "
        f"ret={result['return_pct']:.1f}% win={result['win_rate'] * 100:.1f}% "
        f"tr={result['trades']} dd={result['max_drawdown_pct']:.1f}%"
    )


def run_case(name: str, cfg: BacktestConfig, data_dir: Path) -> dict:
    report_path = Path("reports") / f"robustness_{name}.json"
    report = run_report(data_dir, report_path, cfg)
    return {
        "name": name,
        "path": str(report_path),
        "symbols": report["symbols"],
        "available_days": report["available_days"],
        "audit": report["audit"],
        "windows": report["windows"],
    }


def main() -> None:
    data_dir = Path("../Quantify/data")
    base = BacktestConfig()
    windows = (365, 180, 90, 60, 30, 14, 7)
    cases = [
        (
            "current_15m_preferred",
            replace(base, windows_days=windows),
        ),
        (
            "all_symbols_15m",
            replace(
                base,
                windows_days=windows,
                long_window_preferred_symbols=(),
                active_symbol_limit=8,
                short_window_symbol_limit=16,
            ),
        ),
        (
            "majors_15m",
            replace(
                base,
                windows_days=windows,
                long_window_preferred_symbols=("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP"),
                active_symbol_limit=4,
                short_window_symbol_limit=4,
            ),
        ),
        (
            "available_1h",
            replace(
                base,
                timeframe_minutes=60,
                windows_days=windows,
                long_window_preferred_symbols=(),
                active_symbol_limit=4,
                short_window_symbol_limit=4,
                min_bars=80,
            ),
        ),
        (
            "available_4h",
            replace(
                base,
                timeframe_minutes=240,
                windows_days=(365, 180, 90, 60, 30),
                long_window_preferred_symbols=("BTC-USDT-SWAP", "ETH-USDT-SWAP"),
                active_symbol_limit=2,
                short_window_symbol_limit=2,
                min_bars=40,
            ),
        ),
        (
            "available_1d",
            replace(
                base,
                timeframe_minutes=1440,
                windows_days=(365, 180, 90),
                long_window_preferred_symbols=("BTC-USDT-SWAP", "ETH-USDT-SWAP"),
                active_symbol_limit=2,
                short_window_symbol_limit=2,
                min_bars=30,
            ),
        ),
    ]

    summary = []
    for name, cfg in cases:
        result = run_case(name, cfg, data_dir)
        summary.append(result)
        print(f"\n{name}")
        print(f"  symbols={len(result['symbols'])} available_days={result['available_days']}")
        print(f"  audit={'PASS' if result['audit']['complete'] else 'CHECK'}")
        if result["audit"].get("failures"):
            print("  failures=" + "; ".join(result["audit"]["failures"][:8]))
        for days, window in result["windows"].items():
            print(f"  {days:>3}d {compact_window(window)}")

    Path("reports/robustness_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nsummary=reports/robustness_summary.json")


if __name__ == "__main__":
    main()
