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
    for lookback in (2, 3, 4, 5):
        for min_win in (0.34, 0.50, 0.60, 0.67):
            for pause in (96 * 14, 96 * 30, 96 * 45, 96 * 60, 96 * 90):
                cfg = replace(
                    base,
                    symbol_edge_lookback_trades=lookback,
                    symbol_edge_min_win_rate=min_win,
                    symbol_edge_pause_bars=pause,
                )
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
                        lookback,
                        min_win,
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
    for row in candidates[:60]:
        print(row)


if __name__ == "__main__":
    main()
