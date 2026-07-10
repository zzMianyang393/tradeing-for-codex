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
    for target in (0.009, 0.011, 0.013, 0.015, 0.018, 0.022):
        for floor in (0.35, 0.45, 0.55, 0.65, 0.75):
            for power in (0.75, 1.0, 1.25, 1.5):
                cfg = replace(
                    base,
                    volatility_target_atr_pct=target,
                    volatility_risk_floor=floor,
                    volatility_risk_power=power,
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
                            target,
                            floor,
                            power,
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
    for row in candidates[:40]:
        print(row)


if __name__ == "__main__":
    main()
