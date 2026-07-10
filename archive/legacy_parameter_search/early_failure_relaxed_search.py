from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def payoff(result: dict) -> float:
    wins = [trade for trade in result["trades_detail"] if trade["win"]]
    losses = [trade for trade in result["trades_detail"] if not trade["win"]]
    avg_win = sum(trade["pnl"] for trade in wins) / len(wins) if wins else 0.0
    avg_loss = sum(trade["pnl"] for trade in losses) / len(losses) if losses else 0.0
    return abs(avg_win / avg_loss) if avg_loss else 9.99


def main() -> None:
    base = BacktestConfig()
    market = load_market(Path("../Quantify/data"), base.timeframe_minutes)
    candidates = []
    for bars in (4, 5, 6, 8):
        for min_mfe in (0.0005, 0.0010, 0.0015, 0.0020):
            for max_mae in (0.006, 0.008, 0.010, 0.012, 0.016):
                cfg = replace(
                    base,
                    early_failure_bars=bars,
                    early_failure_min_mfe_pct=min_mfe,
                    early_failure_max_mae_pct=max_mae,
                    early_failure_reasons=("range_revert_long", "range_revert_short"),
                )
                tester = Backtester(cfg)
                r7 = tester.run(market, 7)
                r30 = tester.run(market, 30)
                if (
                    r7["return_pct"] < 20
                    or r30["return_pct"] < 100
                    or r7["win_rate"] < 0.68
                    or r30["win_rate"] < 0.68
                ):
                    continue
                r60 = tester.run(market, 60)
                r90 = tester.run(market, 90)
                r180 = tester.run(market, 180)
                r365 = tester.run(market, 365)
                p60 = payoff(r60)
                p365 = payoff(r365)
                score = (
                    min(r7["return_pct"], 80)
                    + min(r30["return_pct"], 150)
                    + r60["return_pct"]
                    + r90["return_pct"]
                    + min(r180["return_pct"], 150)
                    + r365["return_pct"] * 2.5
                    + p60 * 35
                    + p365 * 35
                    + (r60["win_rate"] + r90["win_rate"] + r180["win_rate"]) * 80
                )
                candidates.append(
                    (
                        score,
                        bars,
                        min_mfe,
                        max_mae,
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
                        p60,
                        p365,
                    )
                )
    candidates.sort(reverse=True)
    for row in candidates[:60]:
        print(row)


if __name__ == "__main__":
    main()
