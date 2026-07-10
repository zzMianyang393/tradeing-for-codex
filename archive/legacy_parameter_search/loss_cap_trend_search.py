from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, float, float, float, float, float, float, float, float, float, float]] = []
    for long_trend, short_trend in (
        (999.0, 999.0),
        (0.1, -0.15),
        (999.0, 0.2),
        (0.1, 0.2),
    ):
        for loss_cap in (999.0, 18.0, 14.0, 12.0, 10.0, 8.0, 6.0):
            cfg = replace(
                base,
                range_long_max_trend_strength=long_trend,
                range_short_max_trend_strength=short_trend,
                max_trade_loss_pct_equity=loss_cap,
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
                score = (
                    (r60["win_rate"] + r90["win_rate"]) * 260
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
                        long_trend,
                        short_trend,
                        loss_cap,
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
