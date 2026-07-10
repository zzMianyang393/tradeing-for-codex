from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = replace(
        BacktestConfig(),
        volatility_target_atr_pct=0.022,
        volatility_risk_floor=0.75,
        volatility_risk_power=0.75,
    )
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, float, float, float, float, float, float, float, float, float]] = []
    for long_mult in (0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 1.0):
        for short_mult in (0.55, 0.70, 0.85, 1.0, 1.15):
            cfg = replace(
                base,
                reason_risk_multipliers={
                    "range_revert_long": long_mult,
                    "range_revert_short": short_mult,
                },
            )
            tester = Backtester(cfg)
            r7 = tester.run(market, 7)
            r30 = tester.run(market, 30)
            if (
                r7["return_pct"] >= 20
                and r30["return_pct"] >= 80
                and r7["win_rate"] >= 0.68
                and r30["win_rate"] >= 0.68
            ):
                r60 = tester.run(market, 60)
                r90 = tester.run(market, 90)
                r180 = tester.run(market, 180)
                r365 = tester.run(market, 365)
                score = (
                    min(r7["return_pct"], 60)
                    + min(r30["return_pct"], 120)
                    + r60["return_pct"]
                    + r90["return_pct"]
                    + r180["return_pct"]
                    + r365["return_pct"]
                )
                candidates.append(
                    (
                        score,
                        long_mult,
                        short_mult,
                        r7["return_pct"],
                        r30["return_pct"],
                        r60["return_pct"],
                        r90["return_pct"],
                        r180["return_pct"],
                        r365["return_pct"],
                        r365["win_rate"],
                    )
                )
    candidates.sort(reverse=True)
    for row in candidates[:30]:
        print(row)


if __name__ == "__main__":
    main()
