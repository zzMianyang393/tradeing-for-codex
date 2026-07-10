from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


WINDOWS = (30, 14, 7)


def compact(result: dict) -> dict:
    keys = ("available", "pnl", "return_pct", "win_rate", "trades", "max_drawdown_pct", "by_reason")
    return {key: result.get(key) for key in keys if key in result}


def score(results: dict[int, dict]) -> float:
    total = 0.0
    for day, weight in ((30, 2.6), (14, 1.0), (7, 2.6)):
        result = results[day]
        ret = float(result.get("return_pct", -999.0))
        win = float(result.get("win_rate", 0.0))
        trades = int(result.get("trades", 0))
        dd = float(result.get("max_drawdown_pct", 100.0))
        target = {30: 50.0, 7: 20.0}.get(day, 0.0)
        total += ((ret - target) + (win - 0.68) * 120.0 - dd * 0.30) * weight
        if trades < 8 and day == 30:
            total -= 35.0
        if ret <= 0:
            total -= 80.0 * weight
    return round(total, 4)


def candidate_configs(base: BacktestConfig, trials: int, seed: int, timeframe: int):
    rng = random.Random(seed)
    fixed = [
        dict(attack_breakout_enabled=True, attack_exhaustion_enabled=False, attack_min_score=3.6),
        dict(attack_breakout_enabled=False, attack_exhaustion_enabled=True, attack_min_score=3.6),
        dict(attack_breakout_enabled=True, attack_exhaustion_enabled=True, attack_min_score=3.8),
        dict(attack_breakout_enabled=True, attack_exhaustion_enabled=False, attack_min_score=4.25, invert_signals=True),
        dict(attack_breakout_enabled=True, attack_exhaustion_enabled=True, attack_min_score=3.6, invert_signals=True),
        dict(
            attack_breakout_enabled=False,
            attack_exhaustion_enabled=True,
            attack_min_score=3.6,
            invert_signals=True,
            attack_risk_per_trade=0.05,
            attack_max_positions=3,
            attack_take_profit_atr=0.65,
            attack_stop_atr=1.05,
            attack_max_hold_bars=45,
        ),
        dict(
            attack_breakout_enabled=False,
            attack_exhaustion_enabled=True,
            attack_min_score=3.6,
            invert_signals=True,
            attack_risk_per_trade=0.08,
            attack_max_positions=3,
            attack_take_profit_atr=0.65,
            attack_stop_atr=1.05,
            attack_max_hold_bars=45,
        ),
        dict(
            attack_breakout_enabled=False,
            attack_exhaustion_enabled=True,
            attack_min_score=3.6,
            invert_signals=True,
            attack_risk_per_trade=0.12,
            attack_max_positions=3,
            attack_take_profit_atr=0.65,
            attack_stop_atr=1.05,
            attack_max_hold_bars=45,
        ),
    ]
    for params in fixed:
        params = dict(params)
        yield replace(
            base,
            timeframe_minutes=timeframe,
            windows_days=WINDOWS,
            min_bars=1200,
            min_score=999.0,
            active_symbol_limit=9,
            short_window_symbol_limit=9,
            short_window_days=30,
            max_positions=0,
            enable_attack_module=True,
            attack_max_positions=params.pop("attack_max_positions", 2),
            attack_risk_per_trade=params.pop("attack_risk_per_trade", 0.025),
            attack_stop_atr=params.pop("attack_stop_atr", 1.2),
            attack_take_profit_atr=params.pop("attack_take_profit_atr", 1.35),
            attack_trailing_atr=0.9,
            attack_max_hold_bars=params.pop("attack_max_hold_bars", 20),
            attack_cooldown_bars=30,
            attack_loss_cooldown_bars=240,
            attack_volume_spike=2.0,
            attack_range_atr=1.2,
            **params,
        )

    for _ in range(max(0, trials - len(fixed))):
        yield replace(
            base,
            timeframe_minutes=timeframe,
            windows_days=WINDOWS,
            min_bars=1200,
            min_score=999.0,
            active_symbol_limit=rng.choice([5, 7, 9]),
            short_window_symbol_limit=9,
            short_window_days=30,
            max_positions=0,
            invert_signals=rng.choice([False, True, True]),
            enable_attack_module=True,
            attack_breakout_enabled=rng.choice([False, True, True]),
            attack_exhaustion_enabled=rng.choice([False, True, True]),
            attack_min_score=rng.choice([3.1, 3.35, 3.6, 3.9, 4.25]),
            attack_risk_per_trade=rng.choice([0.006, 0.01, 0.015, 0.025, 0.04, 0.07]),
            attack_max_positions=rng.choice([1, 2, 3]),
            attack_stop_atr=rng.choice([0.65, 0.85, 1.05, 1.25, 1.55]),
            attack_take_profit_atr=rng.choice([0.65, 0.85, 1.05, 1.35, 1.75, 2.2]),
            attack_trailing_atr=rng.choice([0.35, 0.5, 0.7, 0.9, 1.15]),
            attack_max_hold_bars=rng.choice([5, 8, 12, 20, 30, 45]),
            attack_cooldown_bars=rng.choice([10, 20, 30, 60, 120]),
            attack_loss_cooldown_bars=rng.choice([60, 120, 240, 480, 960]),
            attack_volume_spike=rng.choice([1.6, 2.0, 2.5, 3.0, 3.8]),
            attack_range_atr=rng.choice([0.8, 1.0, 1.25, 1.55, 2.0]),
        )


def print_item(rank: int, item: dict) -> None:
    cfg = item["config"]
    print(
        f"#{rank} score={item['score']} risk={cfg['attack_risk_per_trade']} "
        f"pos={cfg['attack_max_positions']} min={cfg['attack_min_score']} "
        f"tp={cfg['attack_take_profit_atr']} stop={cfg['attack_stop_atr']} "
        f"hold={cfg['attack_max_hold_bars']} breakout={cfg['attack_breakout_enabled']} "
        f"exhaustion={cfg['attack_exhaustion_enabled']}"
    )
    for day in WINDOWS:
        result = item["results"][str(day)]
        if not result.get("available"):
            print(f"  {day:>3}d NA")
            continue
        print(
            f"  {day:>3}d ret={result['return_pct']:>7.2f}% win={result['win_rate'] * 100:>5.1f}% "
            f"tr={result['trades']:>4} dd={result['max_drawdown_pct']:>5.1f}%"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Search a micro attack module on available low-timeframe data.")
    parser.add_argument("--data", type=Path, default=Path("../Quantify/data"))
    parser.add_argument("--timeframe", type=int, default=1)
    parser.add_argument("--trials", type=int, default=48)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260702)
    parser.add_argument("--out", type=Path, default=Path("reports/micro_attack_search.json"))
    args = parser.parse_args()

    base = BacktestConfig()
    market = load_market(args.data, args.timeframe)
    items = []
    print(f"symbols={len(market)} {', '.join(sorted(market))}", flush=True)
    for idx, cfg in enumerate(candidate_configs(base, args.trials, args.seed, args.timeframe), start=1):
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
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"items": items}, indent=2, ensure_ascii=False), encoding="utf-8")
    for rank, item in enumerate(items[: args.top], start=1):
        print_item(rank, item)
    print(f"saved={args.out}")


if __name__ == "__main__":
    main()
