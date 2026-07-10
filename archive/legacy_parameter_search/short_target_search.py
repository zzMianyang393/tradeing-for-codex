from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market
from robust_target_search import ROBUST_WINDOWS, candidate_stream, compact, print_item


SHORT_WINDOWS = (30, 7)


def short_score(results: dict[int, dict]) -> tuple[float, int, float]:
    score = 0.0
    hits = 0
    min_win = 1.0
    targets = {30: 50.0, 7: 20.0}
    for day in SHORT_WINDOWS:
        result = results[day]
        ret = float(result.get("return_pct", -999.0))
        win = float(result.get("win_rate", 0.0))
        trades = int(result.get("trades", 0))
        dd = float(result.get("max_drawdown_pct", 100.0))
        target = targets[day]
        if ret >= target and win >= 0.68:
            hits += 1
        min_win = min(min_win, win)
        score += (ret - target) * 2.0 + (win - 0.68) * 120.0 - dd * 0.35
        if trades < 4:
            score -= 30.0
    return round(score, 4), hits, round(min_win, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search high-return short-window candidates, then audit robustness.")
    parser.add_argument("--data", type=Path, default=Path("../Quantify/data"))
    parser.add_argument("--trials", type=int, default=160)
    parser.add_argument("--top", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260702)
    parser.add_argument("--out", type=Path, default=Path("reports/short_target_search.json"))
    args = parser.parse_args()

    base = BacktestConfig()
    market = load_market(args.data, base.timeframe_minutes)
    stage: list[dict] = []
    for idx, cfg in enumerate(candidate_stream(base, args.trials, args.seed), start=1):
        tester = Backtester(cfg)
        results = {day: tester.run(market, days=day) for day in SHORT_WINDOWS}
        score, hits, min_win = short_score(results)
        item = {
            "trial": idx,
            "score": score,
            "hits": hits,
            "min_win": min_win,
            "_cfg": cfg,
            "config": asdict(cfg),
            "results": {str(day): compact(results[day]) for day in SHORT_WINDOWS},
        }
        stage.append(item)
        if idx == 1 or idx % 10 == 0:
            best = max(stage, key=lambda x: (x["hits"], x["score"]))
            print(f"stage {idx}/{args.trials}: best_hits={best['hits']} best_score={best['score']}", flush=True)

    stage.sort(key=lambda item: (item["hits"], item["score"], item["min_win"]), reverse=True)
    finalists = []
    for item in stage[: args.top]:
        cfg = item["_cfg"]
        tester = Backtester(cfg)
        results = {day: tester.run(market, days=day) for day in ROBUST_WINDOWS}
        final = {
            "trial": item["trial"],
            "short_score": item["score"],
            "short_hits": item["hits"],
            "config": asdict(cfg),
            "results": {str(day): compact(results[day]) for day in ROBUST_WINDOWS},
        }
        finalists.append(final)
        print_item(len(finalists), {"score": item["score"], "passed": item["hits"], "config": asdict(cfg), "results": final["results"]}, ROBUST_WINDOWS)

    payload = {
        "stage": [{key: value for key, value in item.items() if key != "_cfg"} for item in stage[:50]],
        "finalists": finalists,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")


if __name__ == "__main__":
    main()
