from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, float, float, float, int, float, float, float, float, float, float, float, float]] = []
    for stop in (1.6, 2.0, 2.4, 2.8, 3.0):
        for tp in (0.75, 0.9, 1.0, 1.15):
            for trail in (1.4, 1.8, 2.2, 2.55):
                for hold in (3, 4, 5, 6, 8):
                    cfg = replace(
                        base,
                        range_stop_atr=stop,
                        range_take_profit_atr=tp,
                        range_trailing_atr=trail,
                        range_max_hold_bars=hold,
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
                        positive_windows = sum(
                            result["return_pct"] > 0 for result in (r7, r30, r60, r90, r180, r365)
                        )
                        score = (
                            positive_windows * 100
                            + min(r7["return_pct"], 60)
                            + min(r30["return_pct"], 140)
                            + r60["return_pct"] * 1.5
                            + r90["return_pct"] * 1.2
                            + min(r180["return_pct"], 220)
                            + r365["return_pct"]
                        )
                        candidates.append(
                            (
                                score,
                                stop,
                                tp,
                                trail,
                                hold,
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
    for row in candidates[:40]:
        print(row)


if __name__ == "__main__":
    main()
