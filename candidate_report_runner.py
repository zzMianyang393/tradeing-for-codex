from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import run_report
from config import BacktestConfig


def main() -> None:
    cfg = replace(BacktestConfig(), range_long_rsi_max=37.0)
    run_report(Path("../Quantify/data"), Path("reports/auto_switch_v8_range_long_37_candidate.json"), cfg)


if __name__ == "__main__":
    main()
