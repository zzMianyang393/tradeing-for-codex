from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = replace(BacktestConfig(), range_long_rsi_max=37.0)
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, int, int, float, float, float, float, float, float, float, float]] = []
    for loss_cd in (216, 240, 264, 288, 336, 384):
        for pause in (96 * 30, 96 * 45, 96 * 60, 96 * 75, 96 * 90):
            cfg = replace(
                base,
                loss_cooldown_bars=loss_cd,
                symbol_edge_lookback_trades=3,
                symbol_edge_pause_bars=pause,
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
                    + min(r60["return_pct"], 80)
                    + r90["return_pct"]
                    + min(r180["return_pct"], 220)
                    + r365["return_pct"]
                )
                candidates.append(
                    (
                        score,
                        loss_cd,
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
    for row in candidates[:40]:
        print(row)


if __name__ == "__main__":
    main()
