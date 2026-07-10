from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, float, float, float, float, float, float, float, float, float]] = []
    for min_score in (2.45, 2.50, 2.55, 2.60, 2.70):
        for active_limit in (3, 4, 5):
            cfg = replace(base, min_score=min_score, active_symbol_limit=active_limit)
            tester = Backtester(cfg)
            r7 = tester.run(market, 7)
            r30 = tester.run(market, 30)
            if r7["return_pct"] >= 20 and r30["return_pct"] >= 100:
                r60 = tester.run(market, 60)
                r90 = tester.run(market, 90)
                r180 = tester.run(market, 180)
                r365 = tester.run(market, 365)
                score = (
                    (r60["win_rate"] + r90["win_rate"]) * 200
                    + min(r7["return_pct"], 60)
                    + min(r30["return_pct"], 140)
                    + r60["return_pct"]
                    + r90["return_pct"]
                    + min(r180["return_pct"], 220)
                    + r365["return_pct"]
                )
                candidates.append(
                    (
                        score,
                        min_score,
                        active_limit,
                        r7["return_pct"],
                        r30["return_pct"],
                        r60["return_pct"],
                        r90["return_pct"],
                        r180["return_pct"],
                        r365["return_pct"],
                        r60["win_rate"],
                        r90["win_rate"],
                    )
                )
    candidates.sort(reverse=True)
    for row in candidates:
        print(row)


if __name__ == "__main__":
    main()
