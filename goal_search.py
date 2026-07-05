from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def parse_windows(raw: str) -> tuple[int, ...]:
    windows = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not windows:
        raise ValueError("at least one window is required")
    return windows


def score_goal_results(results: dict[int, dict], target_pnl: float) -> tuple[int, float, float, float]:
    pnls = [float(result.get("pnl", -999.0)) for result in results.values()]
    drawdown = max(float(result.get("max_drawdown_pct", 999.0)) for result in results.values())
    passed = sum(1 for pnl in pnls if pnl > target_pnl)
    min_gap = min(pnl - target_pnl for pnl in pnls)
    total_pnl = sum(pnls)
    return passed, round(min_gap, 4), round(total_pnl - drawdown * 0.05, 4), round(-drawdown, 4)


def candidate_stream(base: BacktestConfig, trials: int, seed: int):
    rng = random.Random(seed)
    fixed = [
        {},
        {
            "risk_per_trade": 0.39,
            "max_margin_fraction": 1.95,
            "max_total_margin_fraction": 1.65,
            "excluded_symbols": ("XRP-USDT-SWAP",),
            "profit_lock_equity_fraction": 999.0,
            "profit_lock_risk_multiplier": 1.0,
            "profit_lock_margin_fraction": 1.0,
            "defensive_equity_fraction": 0.0,
        },
        {
            "risk_per_trade": 0.39,
            "max_margin_fraction": 1.95,
            "max_total_margin_fraction": 1.65,
            "excluded_symbols": ("XRP-USDT-SWAP", "BNB-USDT-SWAP", "SUI-USDT-SWAP"),
            "profit_lock_equity_fraction": 999.0,
            "profit_lock_risk_multiplier": 1.0,
            "profit_lock_margin_fraction": 1.0,
            "defensive_equity_fraction": 0.0,
        },
        {
            "risk_per_trade": 2.0,
            "max_margin_fraction": 1.0,
            "max_total_margin_fraction": 1.5,
            "max_positions": 2,
            "active_symbol_limit": 10,
            "short_window_symbol_limit": 8,
            "min_score": 3.05,
            "profit_lock_equity_fraction": 999.0,
            "profit_lock_risk_multiplier": 1.0,
            "profit_lock_margin_fraction": 1.0,
            "defensive_equity_fraction": 0.0,
            "selector_min_avg_quote": 100_000.0,
            "selector_max_micro_noise": 0.008,
            "short_rebound_block_pct": 0.045,
        },
        {
            "enable_continuation_module": True,
            "continuation_risk_per_trade": 0.16,
            "continuation_take_profit_atr": 1.8,
            "continuation_stop_atr": 2.0,
            "continuation_trailing_atr": 1.4,
            "continuation_max_hold_bars": 20,
            "risk_per_trade": 0.39,
            "max_margin_fraction": 1.5,
            "max_total_margin_fraction": 1.25,
            "profit_lock_equity_fraction": 999.0,
            "profit_lock_risk_multiplier": 1.0,
            "profit_lock_margin_fraction": 1.0,
            "defensive_equity_fraction": 0.0,
        },
    ]
    for params in fixed:
        yield replace(base, **params)

    for _ in range(max(0, trials - len(fixed))):
        risk = rng.choice([0.18, 0.24, 0.32, 0.45, 0.65, 0.9, 1.2, 1.6, 2.0])
        yield replace(
            base,
            risk_per_trade=risk,
            max_margin_fraction=rng.choice([0.65, 0.85, 1.0, 1.25, 1.5, 2.0]),
            max_total_margin_fraction=rng.choice([0.55, 0.75, 1.0, 1.25, 1.5, 2.0]),
            max_positions=rng.choice([2, 3, 4, 5, 6]),
            active_symbol_limit=rng.choice([6, 8, 10, 12]),
            short_window_symbol_limit=rng.choice([8, 10, 12, 16, 20]),
            min_score=rng.choice([2.0, 2.2, 2.45, 2.65, 2.85, 3.05, 3.25]),
            profit_lock_equity_fraction=999.0,
            profit_lock_risk_multiplier=1.0,
            profit_lock_margin_fraction=1.0,
            defensive_equity_fraction=0.0,
            max_trade_loss_pct_equity=rng.choice([20.0, 999.0]),
            selector_min_avg_quote=rng.choice([0.0, 50_000.0, 100_000.0, 150_000.0, 250_000.0]),
            selector_max_micro_noise=rng.choice([0.0, 0.0072, 0.008, 0.009, 0.012]),
            selector_volatility_weight=rng.choice([45.0, 70.0, 100.0, 140.0, 180.0]),
            selector_noise_penalty=rng.choice([0.0, 4.0, 6.0, 9.0, 12.0]),
            excluded_symbols=rng.choice(
                [
                    (),
                    ("XRP-USDT-SWAP",),
                    ("BNB-USDT-SWAP",),
                    ("SUI-USDT-SWAP",),
                    ("XRP-USDT-SWAP", "BNB-USDT-SWAP", "SUI-USDT-SWAP"),
                ]
            ),
            transition_long_enabled=rng.choice([False, True]),
            transition_short_enabled=rng.choice([False, True]),
            enable_attack_module=rng.choice([False, True]),
            enable_continuation_module=rng.choice([False, True, True]),
            continuation_risk_per_trade=rng.choice([0.06, 0.10, 0.16, 0.24, 0.32]),
            continuation_min_volume_ratio=rng.choice([1.1, 1.25, 1.45, 1.7]),
            continuation_min_trend_strength=rng.choice([0.8, 1.0, 1.2, 1.5]),
            continuation_take_profit_atr=rng.choice([0.8, 1.2, 1.6, 2.0, 2.6]),
            continuation_stop_atr=rng.choice([1.4, 1.8, 2.2, 2.8]),
            continuation_trailing_atr=rng.choice([1.0, 1.4, 1.8, 2.2]),
            continuation_max_hold_bars=rng.choice([8, 12, 16, 24, 36]),
            attack_risk_per_trade=rng.choice([0.025, 0.05, 0.1, 0.2, 0.4]),
            attack_max_positions=rng.choice([1, 2, 3, 4]),
            short_rebound_block_pct=rng.choice([0.0, 0.015, 0.03, 0.045, 0.08]),
            long_flush_block_pct=rng.choice([-0.08, -0.045, -0.03, -0.015, 0.0]),
            range_take_profit_atr=rng.choice([0.35, 0.55, 0.75, 1.0, 1.25, 1.6]),
            range_stop_atr=rng.choice([1.2, 1.8, 2.4, 3.0, 3.6]),
            range_trailing_atr=rng.choice([0.8, 1.2, 1.56, 2.0, 2.4]),
            cooldown_bars=rng.choice([0, 6, 12, 24, 36, 48]),
            loss_cooldown_bars=rng.choice([24, 48, 96, 144, 240]),
            symbol_edge_lookback_trades=rng.choice([1, 2, 3]),
            symbol_edge_min_win_rate=rng.choice([0.0, 0.34, 0.5, 0.75, 1.0]),
            symbol_edge_pause_bars=rng.choice([96, 96 * 3, 96 * 7, 96 * 14, 96 * 30]),
        )


def compact_result(result: dict) -> dict:
    keys = ("pnl", "return_pct", "win_rate", "max_drawdown_pct", "trades", "from", "to")
    return {key: result[key] for key in keys if key in result}


def compact_config(config: BacktestConfig) -> dict:
    keys = (
        "risk_per_trade",
        "max_margin_fraction",
        "max_total_margin_fraction",
        "max_positions",
        "active_symbol_limit",
        "short_window_symbol_limit",
        "min_score",
        "range_take_profit_atr",
        "range_stop_atr",
        "range_trailing_atr",
        "transition_long_enabled",
        "transition_short_enabled",
        "enable_attack_module",
        "enable_continuation_module",
        "continuation_risk_per_trade",
        "continuation_take_profit_atr",
        "continuation_stop_atr",
        "continuation_min_volume_ratio",
        "continuation_min_trend_strength",
        "selector_min_avg_quote",
        "selector_max_micro_noise",
        "short_rebound_block_pct",
        "excluded_symbols",
    )
    data = asdict(config)
    return {key: data[key] for key in keys}


def main() -> None:
    parser = argparse.ArgumentParser(description="Search configs for absolute pnl targets.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--windows", default="60,30,14")
    parser.add_argument("--target-pnl", type=float, default=10.0)
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260705)
    parser.add_argument("--out", type=Path, default=Path("reports/goal_search.json"))
    args = parser.parse_args()

    windows = parse_windows(args.windows)
    base = BacktestConfig(validation_target_returns={}, validation_target_win_rate=0.0)
    market = load_market(args.data, base.timeframe_minutes)
    top: list[dict] = []
    for idx, config in enumerate(candidate_stream(base, args.trials, args.seed), start=1):
        tester = Backtester(config)
        results = {days: tester.run(market, days=days) for days in windows}
        score = score_goal_results(results, args.target_pnl)
        item = {
            "trial": idx,
            "score": score,
            "config": compact_config(config),
            "results": {str(day): compact_result(results[day]) for day in windows},
        }
        top.append(item)
        top.sort(key=lambda row: row["score"], reverse=True)
        top = top[: args.top]
        if idx == 1 or idx % 5 == 0:
            best = top[0]
            print(f"trial {idx}/{args.trials}: best={best['score']}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"windows": windows, "target_pnl": args.target_pnl, "top": top}, indent=2), encoding="utf-8")
    for rank, item in enumerate(top, start=1):
        print(f"\n#{rank} score={item['score']} trial={item['trial']}", flush=True)
        print(f"  config={item['config']}", flush=True)
        for day in windows:
            result = item["results"][str(day)]
            print(
                f"  {day:>3}d pnl={result['pnl']:>8.4f} ret={result['return_pct']:>8.2f}% "
                f"dd={result['max_drawdown_pct']:>6.2f}% win={result['win_rate'] * 100:>6.2f}% tr={result['trades']:>3}",
                flush=True,
            )
    print(f"\nsaved={args.out}", flush=True)


if __name__ == "__main__":
    main()
