from __future__ import annotations

import argparse
from pathlib import Path

from backtester import run_report
from config import BacktestConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Tradering multi-period backtests.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, default=Path("reports/latest.json"))
    args = parser.parse_args()

    config = BacktestConfig()
    report = run_report(args.data, args.report, config)
    print(f"Data: {report['data_dir']}")
    print(f"Symbols: {', '.join(report['symbols'])}")
    print(f"Available days: {report['available_days']}")
    print(f"Report: {args.report}")
    print()
    for days, result in report["windows"].items():
        if not result.get("available"):
            print(f"{days:>3}d  unavailable  {result['reason']}")
            continue
        status = "PASS" if result["target_pass"] else "CHECK"
        print(
            f"{days:>3}d  {status:5}  equity={result['end_equity']:>8.4f}  "
            f"pnl={result['pnl']:>8.4f}  return={result['return_pct']:>7.3f}%  "
            f"win={result['win_rate'] * 100:>6.2f}%  trades={result['trades']:>4}  "
            f"dd={result['max_drawdown_pct']:>6.2f}%"
        )
    print()
    audit = report.get("audit", {})
    if audit.get("complete"):
        print("AUDIT PASS: all required windows are available, profitable, and above win-rate target.")
    else:
        print("AUDIT CHECK: target is not fully proven yet.")
        for failure in audit.get("failures", []):
            print(f"  - {failure}")


if __name__ == "__main__":
    main()
