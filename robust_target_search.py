from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable

from backtester import Backtester
from config import BacktestConfig
from market import load_market


SHORT_TARGET_RETURN = {7: 20.0, 30: 50.0}
SHORT_TARGET_WIN = 0.68
ROBUST_WINDOWS = (365, 180, 90, 60, 30, 14, 7)
STAGE1_WINDOWS = (60, 30, 7)
WINDOW_WEIGHTS = {365: 0.8, 180: 1.0, 90: 1.0, 60: 1.2, 30: 2.6, 14: 1.0, 7: 2.6}


def candidate_stream(base: BacktestConfig, trials: int, seed: int) -> Iterable[BacktestConfig]:
    rng = random.Random(seed)
    regimes_options = [
        ("range",),
        ("uptrend", "range"),
        ("downtrend", "range"),
        ("uptrend", "downtrend", "range"),
        ("transition", "range"),
        ("uptrend", "downtrend", "range", "transition"),
    ]
    tp_stop_options = [
        (0.45, 1.15),
        (0.60, 1.25),
        (0.80, 1.40),
        (1.00, 1.60),
        (1.25, 1.80),
        (0.42, 2.2),
        (0.55, 2.4),
        (0.70, 2.6),
        (0.85, 2.8),
        (1.00, 3.0),
        (1.20, 3.2),
        (1.45, 3.5),
    ]
    fixed = [
        dict(risk_per_trade=0.16, active_symbol_limit=3, min_score=3.02, take_profit_atr=1.0, stop_atr=2.0),
        dict(risk_per_trade=0.06, active_symbol_limit=3, min_score=3.10, take_profit_atr=0.55, stop_atr=2.4),
        dict(risk_per_trade=0.04, active_symbol_limit=4, min_score=2.85, take_profit_atr=0.70, stop_atr=2.8),
        dict(risk_per_trade=0.08, active_symbol_limit=2, min_score=3.20, take_profit_atr=0.85, stop_atr=3.0),
        dict(risk_per_trade=0.05, active_symbol_limit=5, min_score=2.85, take_profit_atr=1.0, stop_atr=1.6),
        dict(risk_per_trade=0.04, active_symbol_limit=6, min_score=3.20, take_profit_atr=0.8, stop_atr=1.4),
        dict(
            risk_per_trade=0.04,
            active_symbol_limit=8,
            short_window_symbol_limit=8,
            max_positions=2,
            min_score=3.40,
            take_profit_atr=1.0,
            stop_atr=3.0,
            trailing_atr=2.1,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.13,
            active_symbol_limit=5,
            short_window_symbol_limit=5,
            max_positions=2,
            min_score=3.40,
            take_profit_atr=1.0,
            stop_atr=1.6,
            trailing_atr=1.36,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.20,
            active_symbol_limit=5,
            short_window_symbol_limit=5,
            max_positions=2,
            min_score=3.40,
            take_profit_atr=1.0,
            stop_atr=1.6,
            trailing_atr=1.36,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.26,
            active_symbol_limit=5,
            short_window_symbol_limit=5,
            max_positions=2,
            min_score=3.40,
            take_profit_atr=1.0,
            stop_atr=1.6,
            trailing_atr=1.36,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.32,
            active_symbol_limit=5,
            short_window_symbol_limit=5,
            max_positions=2,
            min_score=3.40,
            take_profit_atr=1.0,
            stop_atr=1.6,
            trailing_atr=1.36,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.32,
            active_symbol_limit=5,
            short_window_symbol_limit=12,
            short_window_days=30,
            max_positions=2,
            min_score=3.25,
            take_profit_atr=1.0,
            stop_atr=1.6,
            trailing_atr=1.36,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.32,
            active_symbol_limit=5,
            short_window_symbol_limit=16,
            short_window_days=30,
            max_positions=3,
            min_score=3.15,
            take_profit_atr=1.0,
            stop_atr=1.6,
            trailing_atr=1.36,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.26,
            active_symbol_limit=5,
            short_window_symbol_limit=16,
            short_window_days=30,
            max_positions=3,
            min_score=3.00,
            take_profit_atr=0.85,
            stop_atr=1.6,
            trailing_atr=1.20,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.45,
            active_symbol_limit=5,
            short_window_symbol_limit=20,
            short_window_days=30,
            max_positions=4,
            min_score=2.85,
            take_profit_atr=1.0,
            stop_atr=1.6,
            trailing_atr=1.20,
            enabled_regimes=("downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.36,
            active_symbol_limit=6,
            short_window_symbol_limit=20,
            short_window_days=30,
            max_positions=4,
            min_score=2.65,
            take_profit_atr=0.85,
            stop_atr=1.6,
            trailing_atr=1.05,
            enabled_regimes=("uptrend", "downtrend", "range"),
        ),
        dict(
            risk_per_trade=0.30,
            active_symbol_limit=6,
            short_window_symbol_limit=24,
            short_window_days=30,
            max_positions=4,
            min_score=2.45,
            take_profit_atr=0.70,
            stop_atr=1.4,
            trailing_atr=0.95,
            enabled_regimes=("uptrend", "downtrend", "range", "transition"),
        ),
    ]
    for params in fixed:
        active_limit = params["active_symbol_limit"]
        short_limit = params.get("short_window_symbol_limit", active_limit)
        stop = params["stop_atr"]
        passthrough = {
            key: value
            for key, value in params.items()
            if key not in {"short_window_symbol_limit", "max_positions", "trailing_atr", "enabled_regimes"}
        }
        yield replace(
            base,
            allowed_symbols=(),
            long_window_preferred_symbols=(),
            windows_days=ROBUST_WINDOWS,
            validation_target_win_rate=SHORT_TARGET_WIN,
            enabled_regimes=params.get("enabled_regimes", ("uptrend", "range")),
            short_window_symbol_limit=short_limit,
            max_positions=params.get("max_positions", base.max_positions),
            trailing_atr=params.get("trailing_atr", max(0.9, stop * 0.65)),
            **passthrough,
        )

    for _ in range(max(0, trials - len(fixed))):
        tp, stop = rng.choice(tp_stop_options)
        limit = rng.choice([2, 3, 4, 5, 6, 8])
        cooldown = rng.choice([8, 12, 18, 24, 36, 48, 72])
        cfg = replace(
            base,
            allowed_symbols=(),
            long_window_preferred_symbols=(),
            windows_days=ROBUST_WINDOWS,
            validation_target_win_rate=SHORT_TARGET_WIN,
            risk_per_trade=rng.choice([0.02, 0.03, 0.04, 0.055, 0.075, 0.10, 0.13, 0.16, 0.20, 0.26, 0.32, 0.40, 0.50]),
            max_margin_fraction=rng.choice([0.30, 0.45, 0.60, 0.75, 0.85]),
            max_total_margin_fraction=rng.choice([0.30, 0.45, 0.60, 0.75, 0.85]),
            active_symbol_limit=limit,
            short_window_symbol_limit=rng.choice([limit, min(10, limit + 2), min(12, limit * 2), 16, 20, 24]),
            short_window_days=rng.choice([7, 14, 30]),
            max_positions=rng.choice([1, 1, 2, 3, 4]),
            selector_lookback_bars=rng.choice([96 * 3, 96 * 5, 96 * 7, 96 * 14, 96 * 21]),
            selector_momentum_weight=rng.choice([6.0, 10.0, 16.0, 24.0, 32.0, 44.0]),
            selector_volatility_weight=rng.choice([25.0, 45.0, 70.0, 100.0, 140.0]),
            selector_trend_weight=rng.choice([0.0, 0.12, 0.25, 0.45]),
            selector_noise_penalty=rng.choice([2.0, 4.0, 6.0, 9.0, 12.0]),
            stop_atr=stop,
            take_profit_atr=tp,
            trailing_atr=max(0.65, stop * rng.choice([0.42, 0.55, 0.70, 0.85])),
            max_hold_bars=rng.choice([4, 6, 8, 12, 18, 24, 36]),
            cooldown_bars=cooldown,
            loss_cooldown_bars=rng.choice([cooldown, cooldown * 2, cooldown * 3]),
            min_score=rng.choice([2.20, 2.35, 2.45, 2.65, 2.85, 3.02, 3.20, 3.40]),
            edge_lookback_trades=rng.choice([6, 8, 10, 12, 16]),
            edge_pause_bars=rng.choice([48, 96, 144, 192, 288, 384]),
            symbol_edge_lookback_trades=rng.choice([2, 3, 4]),
            symbol_edge_min_win_rate=rng.choice([0.25, 0.34, 0.50]),
            symbol_edge_pause_bars=rng.choice([96 * 3, 96 * 7, 96 * 14, 96 * 30]),
            invert_signals=rng.choice([False, False, False, True]),
            enabled_regimes=rng.choice(regimes_options),
        )
        yield cfg


def evaluate(tester: Backtester, market: dict, windows: tuple[int, ...]) -> dict[int, dict]:
    return {days: tester.run(market, days=days) for days in windows}


def window_score(day: int, result: dict) -> float:
    if not result.get("available"):
        return -500.0
    ret = float(result.get("return_pct", -100.0))
    win = float(result.get("win_rate", 0.0))
    trades = int(result.get("trades", 0))
    dd = float(result.get("max_drawdown_pct", 0.0))
    target_ret = SHORT_TARGET_RETURN.get(day, 0.0)
    target_win = SHORT_TARGET_WIN if day in (7, 30) else 0.60
    trade_penalty = 20.0 if trades < 4 and day <= 30 else 0.0
    return (ret - target_ret) + (win - target_win) * 140.0 - dd * 0.18 - trade_penalty


def score_results(results: dict[int, dict], windows: tuple[int, ...]) -> tuple[float, int, float, float]:
    score = 0.0
    passed = 0
    min_return = 999.0
    min_win = 999.0
    for day in windows:
        result = results[day]
        score += window_score(day, result) * WINDOW_WEIGHTS.get(day, 1.0)
        if result.get("available"):
            ret = float(result.get("return_pct", -999.0))
            win = float(result.get("win_rate", 0.0))
            min_return = min(min_return, ret)
            min_win = min(min_win, win)
            target_ret = SHORT_TARGET_RETURN.get(day, 0.0)
            target_win = SHORT_TARGET_WIN if day in (7, 30) else 0.60
            if ret > target_ret and win >= target_win:
                passed += 1
    return round(score, 4), passed, round(min_return, 4), round(min_win, 4)


def compact(result: dict) -> dict:
    keys = ("available", "pnl", "return_pct", "win_rate", "trades", "max_drawdown_pct", "from", "to")
    return {key: result.get(key) for key in keys if key in result}


def print_item(rank: int, item: dict, windows: tuple[int, ...]) -> None:
    cfg = item["config"]
    print(
        f"#{rank} score={item['score']} stage_pass={item['passed']} "
        f"risk={cfg['risk_per_trade']} limit={cfg['active_symbol_limit']}/{cfg['short_window_symbol_limit']} "
        f"pos={cfg['max_positions']} tp={cfg['take_profit_atr']} stop={cfg['stop_atr']} "
        f"trail={cfg['trailing_atr']} min_score={cfg['min_score']} regimes={tuple(cfg['enabled_regimes'])}"
        f" invert={cfg['invert_signals']}"
    )
    for day in windows:
        r = item["results"][str(day)]
        if not r.get("available"):
            print(f"  {day:>3}d NA")
            continue
        print(
            f"  {day:>3}d ret={r['return_pct']:>7.2f}% win={r['win_rate'] * 100:>5.1f}% "
            f"tr={r['trades']:>3} dd={r['max_drawdown_pct']:>5.1f}% pnl={r['pnl']:>7.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Search robust Tradering parameters across multiple windows.")
    parser.add_argument("--data", type=Path, default=Path("../Quantify/data"))
    parser.add_argument("--trials", type=int, default=48)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260630)
    parser.add_argument("--out", type=Path, default=Path("reports/robust_target_search.json"))
    args = parser.parse_args()

    base = BacktestConfig()
    market = load_market(args.data, base.timeframe_minutes)
    stage1: list[dict] = []
    for idx, cfg in enumerate(candidate_stream(base, args.trials, args.seed), start=1):
        tester = Backtester(cfg)
        results = evaluate(tester, market, STAGE1_WINDOWS)
        score = score_results(results, STAGE1_WINDOWS)
        item = {
            "trial": idx,
            "score": score[0],
            "passed": score[1],
            "min_return": score[2],
            "min_win": score[3],
            "_cfg": cfg,
            "config": asdict(cfg),
            "results": {str(day): compact(results[day]) for day in STAGE1_WINDOWS},
        }
        stage1.append(item)
        if idx == 1 or idx % 5 == 0:
            print(f"stage1 {idx}/{args.trials}: best={max(stage1, key=lambda x: x['score'])['score']}", flush=True)

    stage1.sort(key=lambda item: (item["score"], item["passed"], item["min_return"], item["min_win"]), reverse=True)
    finalists: list[dict] = []
    for item in stage1[: args.top]:
        cfg = item["_cfg"]
        tester = Backtester(cfg)
        results = evaluate(tester, market, ROBUST_WINDOWS)
        score = score_results(results, ROBUST_WINDOWS)
        final = {
            "trial": item["trial"],
            "score": score[0],
            "passed": score[1],
            "min_return": score[2],
            "min_win": score[3],
            "config": asdict(cfg),
            "results": {str(day): compact(results[day]) for day in ROBUST_WINDOWS},
        }
        finalists.append(final)
        print_item(len(finalists), final, ROBUST_WINDOWS)

    finalists.sort(key=lambda item: (item["score"], item["passed"], item["min_return"], item["min_win"]), reverse=True)
    stage1_json = [{key: value for key, value in item.items() if key != "_cfg"} for item in stage1[:30]]
    payload = {"stage1": stage1_json, "finalists": finalists}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    if finalists:
        print("\nBEST")
        print_item(1, finalists[0], ROBUST_WINDOWS)


if __name__ == "__main__":
    main()
