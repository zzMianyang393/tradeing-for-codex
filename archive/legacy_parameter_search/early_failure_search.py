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
    reason_sets = (
        ("range_revert_long", "range_revert_short"),
        ("range_revert_long", "range_revert_short", "transition_breakout_long", "transition_breakout_short"),
    )
    for reasons in reason_sets:
        for bars in (2, 3, 4, 5):
            for min_mfe in (0.0015, 0.0025, 0.0035, 0.0050):
                for max_mae in (0.0025, 0.0040, 0.0060, 0.0080):
                    cfg = replace(
                        base,
                        early_failure_bars=bars,
                        early_failure_min_mfe_pct=min_mfe,
                        early_failure_max_mae_pct=max_mae,
                        early_failure_reasons=reasons,
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
                    if (
                        r60["return_pct"] <= 0
                        or r90["return_pct"] <= 0
                        or r60["win_rate"] < 0.68
                        or r90["win_rate"] < 0.68
                    ):
                        continue
                    r180 = tester.run(market, 180)
                    r365 = tester.run(market, 365)
                    if r180["return_pct"] <= 0 or r180["win_rate"] < 0.68:
                        continue
                    p60 = payoff(r60)
                    p365 = payoff(r365)
                    score = (
                        min(r7["return_pct"], 80)
                        + min(r30["return_pct"], 150)
                        + r60["return_pct"] * 1.2
                        + r90["return_pct"]
                        + min(r180["return_pct"], 150)
                        + r365["return_pct"] * 2.5
                        + p60 * 40
                        + p365 * 40
                    )
                    candidates.append(
                        (
                            score,
                            reasons,
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
                            r365["win_rate"],
                            p60,
                            p365,
                        )
                    )
    candidates.sort(reverse=True)
    for row in candidates[:50]:
        print(row)


if __name__ == "__main__":
    main()
