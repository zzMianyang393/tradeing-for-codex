from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from backtester import run_report
from config import BacktestConfig, SymbolRisk
from market import load_market


def compact_window(result: dict) -> str:
    if not result.get("available"):
        return "NA"
    status = "PASS" if result.get("target_pass") else "CHECK"
    return (
        f"{status:5} equity={result['end_equity']:>8.4f} "
        f"pnl={result['pnl']:>8.4f} ret={result['return_pct']:>7.2f}% "
        f"win={result['win_rate'] * 100:>6.2f}% tr={result['trades']:>4} "
        f"dd={result['max_drawdown_pct']:>6.2f}%"
    )


def aggressive_all_windows_config(config: BacktestConfig, symbols: tuple[str, ...]) -> BacktestConfig:
    return replace(
        config,
        enable_long_window_aggressive_profile=False,
        cooldown_bars=config.long_window_aggressive_cooldown_bars,
        max_margin_fraction=config.long_window_aggressive_max_margin_fraction,
        max_total_margin_fraction=config.long_window_aggressive_max_total_margin_fraction,
        profit_lock_equity_fraction=999.0,
        profit_lock_risk_multiplier=1.0,
        profit_lock_margin_fraction=1.0,
        leverage_caps={
            symbol: SymbolRisk(config.long_window_aggressive_leverage)
            for symbol in symbols
        },
    )


def conservative_all_windows_config(config: BacktestConfig) -> BacktestConfig:
    return replace(
        config,
        enable_long_window_aggressive_profile=False,
        long_window_preferred_symbols=(),
    )


def run_case(name: str, data_dir: Path, config: BacktestConfig) -> dict:
    report_path = Path("reports") / f"overfit_{name}.json"
    report = run_report(data_dir, report_path, config)
    return {
        "name": name,
        "path": str(report_path),
        "audit": report["audit"],
        "windows": report["windows"],
    }


def print_case(case: dict) -> None:
    print(f"\n{case['name']}", flush=True)
    print(f"  report={case['path']}", flush=True)
    print(f"  audit={'PASS' if case['audit']['complete'] else 'CHECK'}", flush=True)
    for failure in case["audit"].get("failures", [])[:10]:
        print(f"  - {failure}", flush=True)
    for days, result in case["windows"].items():
        print(f"  {days:>3}d {compact_window(result)}", flush=True)


def main() -> None:
    data_dir = Path("data")
    base = BacktestConfig()
    market = load_market(data_dir, base.timeframe_minutes)
    symbols = tuple(sorted(market))
    cases = [
        ("window_specific_current", base),
        ("same_conservative_all_windows", conservative_all_windows_config(base)),
        ("same_aggressive_all_windows", aggressive_all_windows_config(base, symbols)),
    ]

    summary = []
    for name, config in cases:
        case = run_case(name, data_dir, config)
        summary.append(case)
        print_case(case)

    summary_path = Path("reports/overfit_audit_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsummary={summary_path}", flush=True)


if __name__ == "__main__":
    main()
