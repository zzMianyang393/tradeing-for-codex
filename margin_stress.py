from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def compact(result: dict) -> dict:
    keys = ("available", "pnl", "return_pct", "win_rate", "trades", "max_drawdown_pct", "from", "to")
    return {key: result.get(key) for key in keys if key in result}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stress-test margin caps without changing the production config.")
    parser.add_argument("--data", type=Path, default=Path("../Quantify/data"))
    parser.add_argument("--out", type=Path, default=Path("reports/margin_stress.json"))
    args = parser.parse_args()

    base = BacktestConfig()
    market = load_market(args.data, base.timeframe_minutes)
    windows = (365, 180, 90, 60, 30, 14, 7)
    candidates = []
    for margin in (0.85, 1.0, 1.15, 1.35, 1.6, 2.0):
        for total_margin in (margin, max(margin, 1.0), max(margin, 1.35), max(margin, 1.6), max(margin, 2.0)):
            for positions in (2, 3, 4):
                cfg = replace(
                    base,
                    max_margin_fraction=margin,
                    max_total_margin_fraction=total_margin,
                    max_positions=positions,
                )
                tester = Backtester(cfg)
                results = {str(day): compact(tester.run(market, days=day)) for day in windows}
                score = (
                    results["7"]["return_pct"]
                    + results["30"]["return_pct"]
                    + (results["7"]["win_rate"] - 0.68) * 100
                    + (results["30"]["win_rate"] - 0.68) * 100
                    - max(0.0, results["365"]["max_drawdown_pct"] - 55.0)
                )
                candidates.append(
                    {
                        "score": round(score, 4),
                        "config": asdict(cfg),
                        "results": results,
                    }
                )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    payload = {"candidates": candidates[:30]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    for rank, item in enumerate(candidates[:12], start=1):
        cfg = item["config"]
        print(
            f"#{rank} score={item['score']} margin={cfg['max_margin_fraction']} "
            f"total={cfg['max_total_margin_fraction']} pos={cfg['max_positions']}"
        )
        for day in (365, 30, 7):
            r = item["results"][str(day)]
            print(
                f"  {day:>3}d ret={r['return_pct']:>7.2f}% "
                f"win={r['win_rate'] * 100:>5.1f}% tr={r['trades']:>3} dd={r['max_drawdown_pct']:>5.1f}%"
            )
    print(f"saved={args.out}")


if __name__ == "__main__":
    main()
