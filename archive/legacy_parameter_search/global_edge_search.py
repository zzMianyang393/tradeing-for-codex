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
    for lookback in (6, 8, 10, 12, 15):
        for pause in (96, 192, 288, 480, 672, 960):
            cfg = replace(base, edge_lookback_trades=lookback, edge_pause_bars=pause)
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
                + r365["win_rate"] * 140
            )
            candidates.append(
                (
                    score,
                    lookback,
                    pause,
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
    for row in candidates[:50]:
        print(row)


if __name__ == "__main__":
    main()
