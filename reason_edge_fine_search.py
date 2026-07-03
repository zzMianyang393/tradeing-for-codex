from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, int, float, int, float, float, float, float, float, float, float, float]] = []
    for lookback in (5, 6, 7, 8):
        for min_win in (0.34, 0.45, 0.50, 0.55):
            for pause in (960, 1152, 1344, 1536, 1728, 2016):
                cfg = replace(
                    base,
                    reason_edge_lookback_trades=lookback,
                    reason_edge_min_win_rate=min_win,
                    reason_edge_pause_bars=pause,
                )
                tester = Backtester(cfg)
                r7 = tester.run(market, 7)
                r30 = tester.run(market, 30)
                if (
                    r7["return_pct"] >= 20
                    and r30["return_pct"] >= 100
                    and r7["win_rate"] >= 0.68
                    and r30["win_rate"] >= 0.68
                ):
                    r60 = tester.run(market, 60)
                    r90 = tester.run(market, 90)
                    r180 = tester.run(market, 180)
                    r365 = tester.run(market, 365)
                    if r60["win_rate"] < 0.68 or r90["win_rate"] < 0.68 or r60["return_pct"] <= 0 or r90["return_pct"] <= 0:
                        continue
                    score = (
                        min(r7["return_pct"], 80)
                        + min(r30["return_pct"], 150)
                        + r60["return_pct"]
                        + r90["return_pct"]
                        + min(r180["return_pct"], 150)
                        + r365["return_pct"] * 2.5
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
                            r60["win_rate"],
                            r90["win_rate"],
                        )
                    )
    candidates.sort(reverse=True)
    for row in candidates[:50]:
        print(row)


if __name__ == "__main__":
    main()
