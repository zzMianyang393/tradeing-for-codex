from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    out = []
    for long_enabled in (True, False):
        for short_enabled in (True, False):
            cfg = replace(
                base,
                transition_long_enabled=long_enabled,
                transition_short_enabled=short_enabled,
            )
            tester = Backtester(cfg)
            r7 = tester.run(market, 7)
            r30 = tester.run(market, 30)
            r60 = tester.run(market, 60)
            r90 = tester.run(market, 90)
            r180 = tester.run(market, 180)
            r365 = tester.run(market, 365)
            out.append(
                (
                    long_enabled,
                    short_enabled,
                    r7["return_pct"],
                    r30["return_pct"],
                    r60["return_pct"],
                    r90["return_pct"],
                    r180["return_pct"],
                    r365["return_pct"],
                    r60["win_rate"],
                    r90["win_rate"],
                    r180["win_rate"],
                    r365["win_rate"],
                )
            )
    for row in out:
        print(row)


if __name__ == "__main__":
    main()
