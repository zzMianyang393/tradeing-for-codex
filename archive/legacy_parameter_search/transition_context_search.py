from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates = []
    for threshold in (-1.0, -0.30, -0.20, -0.12, -0.08, -0.04, 0.0, 0.04):
        cfg = replace(base, transition_long_min_move_21d=threshold)
        tester = Backtester(cfg)
        r7 = tester.run(market, 7)
        r30 = tester.run(market, 30)
        if (
            r7["return_pct"] < 20
            or r30["return_pct"] < 100
            or r7["win_rate"] < 0.68
            or r30["win_rate"] < 0.68
        ):
            continue
        r60 = tester.run(market, 60)
        r90 = tester.run(market, 90)
        r180 = tester.run(market, 180)
        r365 = tester.run(market, 365)
        if r60["return_pct"] <= 0 or r90["return_pct"] <= 0 or r60["win_rate"] < 0.68 or r90["win_rate"] < 0.68:
            continue
        score = (
            min(r7["return_pct"], 80)
            + min(r30["return_pct"], 150)
            + r60["return_pct"]
            + r90["return_pct"]
            + min(r180["return_pct"], 150)
            + r365["return_pct"] * 3
            + r365["win_rate"] * 100
        )
        candidates.append(
            (
                score,
                threshold,
                r7["return_pct"],
                r30["return_pct"],
                r60["return_pct"],
                r90["return_pct"],
                r180["return_pct"],
                r365["return_pct"],
                r365["win_rate"],
                r60["win_rate"],
                r90["win_rate"],
            )
        )
    candidates.sort(reverse=True)
    for row in candidates:
        print(row)


if __name__ == "__main__":
    main()
