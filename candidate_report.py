from __future__ import annotations

import argparse
import json
from pathlib import Path

from backtester import run_report
from config import BacktestConfig, SymbolRisk


def restore_config(payload: dict) -> BacktestConfig:
    config = dict(payload)
    leverage_caps = config.get("leverage_caps", {})
    config["leverage_caps"] = {
        symbol: value if isinstance(value, SymbolRisk) else SymbolRisk(**value)
        for symbol, value in leverage_caps.items()
    }
    return BacktestConfig(**config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a detailed report for a robust search finalist.")
    parser.add_argument("search_report", type=Path)
    parser.add_argument("--rank", type=int, default=1)
    parser.add_argument("--data", type=Path, default=Path("../Quantify/data"))
    parser.add_argument("--out", type=Path, default=Path("reports/candidate_detail.json"))
    args = parser.parse_args()

    search = json.loads(args.search_report.read_text(encoding="utf-8"))
    finalists = sorted(
        search["finalists"],
        key=lambda item: (item["score"], item["passed"], item["min_return"], item["min_win"]),
        reverse=True,
    )
    cfg = restore_config(finalists[args.rank - 1]["config"])
    report = run_report(args.data, args.out, cfg)
    print(f"saved={args.out}")
    for days, result in report["windows"].items():
        if not result.get("available"):
            print(f"{days}d NA {result.get('reason')}")
            continue
        print(
            f"{days}d ret={result['return_pct']:.2f}% win={result['win_rate'] * 100:.1f}% "
            f"tr={result['trades']} dd={result['max_drawdown_pct']:.1f}% pnl={result['pnl']:.3f}"
        )


if __name__ == "__main__":
    main()
