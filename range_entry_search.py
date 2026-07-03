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
    for long_max in (34.0, 35.0, 36.0, 37.0):
        for short_min in (64.0, 65.0, 66.0, 67.0):
            for vol_max in (1.45, 1.6, 1.7):
                cfg = replace(
                    base,
                    range_long_rsi_max=long_max,
                    range_short_rsi_min=short_min,
                    range_max_volume_ratio=vol_max,
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
                            long_max,
                            short_min,
                            vol_max,
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
