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
    for trigger in (0.75, 0.80, 0.85, 0.90, 0.95):
        for risk_mult in (0.35, 0.50, 0.65, 0.80):
            for margin in (0.12, 0.18, 0.25, 0.35):
                cfg = replace(
                    base,
                    defensive_equity_fraction=trigger,
                    defensive_risk_multiplier=risk_mult,
                    defensive_margin_fraction=margin,
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
                    if r60["return_pct"] <= 0 or r90["return_pct"] <= 0 or r60["win_rate"] < 0.68 or r90["win_rate"] < 0.68:
                        continue
                    score = (
                        min(r7["return_pct"], 80)
                        + min(r30["return_pct"], 150)
                        + r60["return_pct"]
                        + r90["return_pct"]
                        + min(r180["return_pct"], 150)
                        + r365["return_pct"] * 3
                    )
                    candidates.append(
                        (
                            score,
                            trigger,
                            risk_mult,
                            margin,
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
