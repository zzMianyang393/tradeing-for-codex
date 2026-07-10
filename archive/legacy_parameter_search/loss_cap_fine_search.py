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
    for long_trend in (0.0, 0.1, 0.2, 0.35):
        for short_trend in (-0.25, -0.15, -0.05, 0.0, 0.1):
            for loss_cap in (15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 22.0):
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
                        (r60["win_rate"] + r90["win_rate"]) * 320
                        + min(r7["return_pct"], 80)
                        + min(r30["return_pct"], 160)
                        + r60["return_pct"]
                        + r90["return_pct"]
                        + min(r180["return_pct"], 120)
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
    for row in candidates[:60]:
        print(row)


if __name__ == "__main__":
    main()
