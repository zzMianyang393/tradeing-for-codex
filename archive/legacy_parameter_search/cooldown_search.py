from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, int, int, int, float, float, float, float, float, float, float, float]] = []
    for loss_cd in (192, 288, 384, 576, 768, 960, 1344):
        for symbol_lookback in (2, 3, 4):
            for symbol_pause in (96 * 14, 96 * 30, 96 * 60, 96 * 90):
                cfg = replace(
                    base,
                    loss_cooldown_bars=loss_cd,
                    symbol_edge_lookback_trades=symbol_lookback,
                    symbol_edge_pause_bars=symbol_pause,
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
                            loss_cd,
                            symbol_lookback,
                            symbol_pause,
                            r7["return_pct"],
                            r30["return_pct"],
                            r60["return_pct"],
                            r90["return_pct"],
                            r180["return_pct"],
                            r365["return_pct"],
                            r7["win_rate"],
                            r30["win_rate"],
                        )
                    )
    candidates.sort(reverse=True)
    for row in candidates[:40]:
        print(row)


if __name__ == "__main__":
    main()
