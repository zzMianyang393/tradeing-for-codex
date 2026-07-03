from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def score_result(result: dict) -> float:
    if not result.get("available") or result["trades"] < 12:
        return -1_000_000.0
    return (
        result["return_pct"] * 2.0
        + result["win_rate"] * 80.0
        - result["max_drawdown_pct"] * 1.4
        + min(result["trades"], 90) * 0.04
    )


def main() -> None:
    data_dir = Path("../okx_historical_data/okx_historical_data")
    base = BacktestConfig()
    market = load_market(data_dir, base.timeframe_minutes)
    candidates = []
    for min_score in (2.55, 2.75, 3.0):
        for risk in (0.0025, 0.0035):
            for stop_atr in (1.9, 2.35, 2.8):
                for tp_atr in (0.38, 0.52, 0.7):
                    for hold in (6, 10, 14):
                        cfg = replace(
                            base,
                            min_score=min_score,
                            risk_per_trade=risk,
                            stop_atr=stop_atr,
                            take_profit_atr=tp_atr,
                            trailing_atr=max(0.55, stop_atr * 0.85),
                            max_hold_bars=hold,
                            max_positions=3,
                            max_margin_fraction=0.11,
                            max_total_margin_fraction=0.42,
                        )
                        tester = Backtester(cfg)
                        results = [tester.run(market, days=days) for days in (90, 60, 30, 7)]
                        passes = sum(1 for r in results if r.get("target_pass"))
                        worst_return = min(r.get("return_pct", -999) for r in results)
                        avg_score = sum(score_result(r) for r in results) / len(results)
                        candidates.append((passes, worst_return, avg_score, cfg, results))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    for rank, (passes, worst_return, avg_score, cfg, results) in enumerate(candidates[:20], start=1):
        print(
            f"#{rank:02d} pass={passes}/4 worst={worst_return:.2f}% score={avg_score:.2f} "
            f"min_score={cfg.min_score} risk={cfg.risk_per_trade} stop={cfg.stop_atr} "
            f"tp={cfg.take_profit_atr} hold={cfg.max_hold_bars}"
        )
        print(
            "    "
            + " | ".join(
                f"{r['days']}d ret={r['return_pct']:.2f}% win={r['win_rate']*100:.1f}% tr={r['trades']} dd={r['max_drawdown_pct']:.1f}%"
                for r in results
            )
        )


if __name__ == "__main__":
    main()
