"""Walk-forward validation for pairs research.

Pair eligibility is decided only from a formation period.  The following test
period uses the frozen pair decision and the no-lookahead execution semantics
from :mod:`pairs_backtester`.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

from config import BacktestConfig
from pairs_backtester import PairsBacktester


@dataclass(frozen=True)
class FormationStats:
    pair: str
    observations: int
    coint_pvalue: float
    beta: float
    half_life_bars: float


def formation_stats(pair: str, frame: pd.DataFrame) -> FormationStats:
    s1, s2 = pair.split("-")
    y = np.log(frame[s1].astype(float).to_numpy())
    x = np.log(frame[s2].astype(float).to_numpy())
    _, pvalue, _ = coint(y, x)
    model = sm.OLS(y, sm.add_constant(x)).fit()
    residual = y - model.predict(sm.add_constant(x))
    lagged, delta = residual[:-1], np.diff(residual)
    reversion = sm.OLS(delta, sm.add_constant(lagged)).fit().params[1] if len(delta) else 0.0
    half_life = -math.log(2.0) / reversion if reversion < 0 else math.inf
    return FormationStats(pair, len(frame), float(pvalue), float(model.params[1]), float(half_life))


def validate_pair(
    tester: PairsBacktester,
    pair: str,
    frame: pd.DataFrame,
    formation_bars: int,
    test_bars: int,
    folds: int,
    max_pvalue: float,
    max_half_life_bars: float,
) -> dict[str, Any]:
    if len(frame) < formation_bars + test_bars * folds:
        return {"pair": pair, "error": "insufficient_overlap"}
    results: list[dict[str, Any]] = []
    first_test_start = len(frame) - test_bars * folds
    for fold in range(folds):
        test_start = first_test_start + fold * test_bars
        test_end = test_start + test_bars
        formation = frame.iloc[test_start - formation_bars : test_start]
        stats = formation_stats(pair, formation)
        accepted = stats.coint_pvalue <= max_pvalue and stats.half_life_bars <= max_half_life_bars
        item: dict[str, Any] = {"fold": fold + 1, "formation": asdict(stats), "accepted": accepted}
        if accepted:
            s1, s2 = pair.split("-")
            indicators = tester.calculate_indicators(s1, s2, frame.iloc[:test_end])
            item["test"] = tester.run_trading_simulation(s1, s2, indicators, window_bars=test_bars)
        results.append(item)
    accepted_tests = [item["test"] for item in results if item["accepted"] and "test" in item]
    return {
        "pair": pair,
        "formation_bars": formation_bars,
        "test_bars": test_bars,
        "folds": results,
        "accepted_folds": len(accepted_tests),
        "total_test_return_pct": round(sum(item["net_profit_pct"] for item in accepted_tests), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pairs with formation/test walk-forward splits.")
    parser.add_argument("--pairs", required=True, help="Comma-separated candidate pairs, e.g. FIL-OP,ARB-AVAX")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--formation-bars", type=int, default=96 * 180)
    parser.add_argument("--test-bars", type=int, default=96 * 90)
    parser.add_argument("--folds", type=int, default=3)
    parser.add_argument("--max-pvalue", type=float, default=0.05)
    parser.add_argument("--max-half-life-bars", type=float, default=96 * 14)
    parser.add_argument("--out", type=Path, default=Path("reports/pairs_walk_forward.json"))
    args = parser.parse_args(argv)
    tester = PairsBacktester(BacktestConfig())
    output: dict[str, Any] = {"execution_semantics": "formation_then_next_bar_execution_v1", "pairs": {}}
    for pair in (item.strip() for item in args.pairs.split(",") if item.strip()):
        s1, s2 = pair.split("-", 1)
        frame = tester.load_and_align_prices(s1, s2, args.data)
        output["pairs"][pair] = validate_pair(
            tester, pair, frame, args.formation_bars, args.test_bars, args.folds,
            args.max_pvalue, args.max_half_life_bars,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
