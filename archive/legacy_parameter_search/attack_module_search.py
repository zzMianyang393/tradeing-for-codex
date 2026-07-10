from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


WINDOWS = (365, 180, 90, 60, 30, 7)


def compact(result: dict) -> dict:
    keys = ("available", "pnl", "return_pct", "win_rate", "trades", "max_drawdown_pct", "by_reason")
    return {key: result.get(key) for key in keys if key in result}


def score(results: dict[int, dict]) -> float:
    total = 0.0
    for day, weight in ((365, 0.8), (180, 1.0), (90, 1.0), (60, 1.2), (30, 2.5), (7, 2.5)):
        result = results[day]
        ret = float(result.get("return_pct", -999.0))
        win = float(result.get("win_rate", 0.0))
        dd = float(result.get("max_drawdown_pct", 100.0))
        target = {30: 50.0, 7: 20.0}.get(day, 0.0)
        total += ((ret - target) + (win - 0.68) * 120.0 - dd * 0.25) * weight
        if ret <= 0:
            total -= 120.0 * weight
    return round(total, 4)


def candidate_configs(base: BacktestConfig, trials: int, seed: int):
    rng = random.Random(seed)
    fixed = [
        dict(enable_attack_module=True, attack_breakout_enabled=False, attack_exhaustion_enabled=True),
        dict(enable_attack_module=True, attack_breakout_enabled=True, attack_exhaustion_enabled=False),
        dict(enable_attack_module=True, attack_breakout_enabled=True, attack_exhaustion_enabled=True),
    ]
    for params in fixed:
        yield replace(base, **params)
    for _ in range(max(0, trials - len(fixed))):
        yield replace(
            base,
            enable_attack_module=True,
            attack_breakout_enabled=rng.choice([False, False, True]),
            attack_exhaustion_enabled=rng.choice([False, True, True]),
            attack_min_score=rng.choice([3.25, 3.45, 3.7, 4.0, 4.35]),
            attack_risk_per_trade=rng.choice([0.006, 0.01, 0.015, 0.025, 0.04, 0.07]),
            attack_max_positions=rng.choice([1, 1, 2]),
            attack_stop_atr=rng.choice([0.65, 0.85, 1.05, 1.25, 1.55]),
            attack_take_profit_atr=rng.choice([0.75, 1.0, 1.25, 1.55, 2.0]),
            attack_trailing_atr=rng.choice([0.45, 0.65, 0.85, 1.05, 1.3]),
            attack_max_hold_bars=rng.choice([2, 3, 4, 6, 8]),
            attack_cooldown_bars=rng.choice([6, 12, 24, 48]),
            attack_loss_cooldown_bars=rng.choice([48, 96, 192, 384]),
            attack_volume_spike=rng.choice([1.6, 1.9, 2.2, 2.8, 3.4]),
            attack_range_atr=rng.choice([0.9, 1.1, 1.35, 1.7]),
        )


def print_item(rank: int, item: dict) -> None:
    cfg = item["config"]
    print(
        f"#{rank} score={item['score']} risk={cfg['attack_risk_per_trade']} "
        f"pos={cfg['attack_max_positions']} min={cfg['attack_min_score']} "
        f"tp={cfg['attack_take_profit_atr']} stop={cfg['attack_stop_atr']} "
        f"breakout={cfg['attack_breakout_enabled']} exhaustion={cfg['attack_exhaustion_enabled']}"
    )
    for day in WINDOWS:
        r = item["results"][str(day)]
        print(
            f"  {day:>3}d ret={r['return_pct']:>7.2f}% win={r['win_rate'] * 100:>5.1f}% "
            f"tr={r['trades']:>3} dd={r['max_drawdown_pct']:>5.1f}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Search attack-module overlay parameters.")
    parser.add_argument("--data", type=Path, default=Path("../Quantify/data"))
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260702)
    parser.add_argument("--out", type=Path, default=Path("reports/attack_module_search.json"))
    args = parser.parse_args()

    base = BacktestConfig()
    market = load_market(args.data, base.timeframe_minutes)
    items = []
    for idx, cfg in enumerate(candidate_configs(base, args.trials, args.seed), start=1):
        tester = Backtester(cfg)
        results = {day: tester.run(market, days=day) for day in WINDOWS}
        item = {
            "trial": idx,
            "score": score(results),
            "config": asdict(cfg),
            "results": {str(day): compact(results[day]) for day in WINDOWS},
        }
        items.append(item)
        if idx == 1 or idx % 5 == 0:
            print(f"trial {idx}/{args.trials}: best={max(items, key=lambda x: x['score'])['score']}", flush=True)

    items.sort(key=lambda item: item["score"], reverse=True)
    payload = {"items": items}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for rank, item in enumerate(items[: args.top], start=1):
        print_item(rank, item)
    print(f"saved={args.out}")


if __name__ == "__main__":
    main()
