from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates: list[tuple[float, int, int, bool, float, float, float, float, float, float, float, float]] = []
    for loss_cd, pause in ((216, 96 * 60), (240, 96 * 30), (240, 96 * 60), (288, 96 * 60)):
        for breakout_enabled, attack_score, attack_risk in (
            (False, 4.0, 0.025),
            (True, 4.2, 0.015),
            (True, 4.2, 0.04),
            (True, 4.5, 0.025),
            (True, 4.5, 0.06),
        ):
            cfg = replace(
                base,
                loss_cooldown_bars=loss_cd,
                symbol_edge_lookback_trades=3,
                symbol_edge_pause_bars=pause,
                attack_breakout_enabled=breakout_enabled,
                attack_min_score=attack_score,
                attack_risk_per_trade=attack_risk,
            )
            tester = Backtester(cfg)
            r7 = tester.run(market, 7)
            r30 = tester.run(market, 30)
            if r7["return_pct"] < 20 or r30["return_pct"] < 100:
                continue
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
                + r60["return_pct"]
                + r90["return_pct"]
                + min(r180["return_pct"], 250)
                + r365["return_pct"]
            )
            candidates.append(
                (
                    score,
                    loss_cd,
                    pause,
                    breakout_enabled,
                    attack_score,
                    attack_risk,
                    r7["return_pct"],
                    r30["return_pct"],
                    r60["return_pct"],
                    r90["return_pct"],
                    r180["return_pct"],
                    r365["return_pct"],
                )
            )
    candidates.sort(reverse=True)
    for row in candidates:
        print(row)


if __name__ == "__main__":
    main()
