from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = replace(
        BacktestConfig(),
        loss_cooldown_bars=288,
        symbol_edge_lookback_trades=3,
        symbol_edge_pause_bars=96 * 60,
    )
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, float, float, float, float, float, float, float, float, float]] = []
    for risk in (0.32, 0.34, 0.36, 0.38, 0.40, 0.44):
        for margin in (0.60, 0.65, 0.70, 0.75):
            cfg = replace(base, risk_per_trade=risk, max_margin_fraction=margin)
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
                    min(r7["return_pct"], 60)
                    + min(r30["return_pct"], 140)
                    + r60["return_pct"]
                    + r90["return_pct"]
                    + min(r180["return_pct"], 250)
                    + r365["return_pct"]
                )
                candidates.append(
                    (
                        score,
                        risk,
                        margin,
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
