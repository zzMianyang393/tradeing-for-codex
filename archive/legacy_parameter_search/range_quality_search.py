from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, float, float, float, float, float, float, float, float, float, float, float]] = []
    for body_max in (1.0, 0.010, 0.008, 0.006, 0.005):
        for range_max in (1.0, 0.018, 0.014, 0.011):
            for short_move in (-1.0, 0.0, 0.004, 0.008, 0.012):
                cfg = replace(
                    base,
                    range_long_max_body_pct=body_max,
                    range_long_max_range_pct=range_max,
                    range_short_min_move_1d=short_move,
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
                        positive_windows * 120
                        + (r60["win_rate"] + r90["win_rate"]) * 180
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
                            body_max,
                            range_max,
                            short_move,
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
