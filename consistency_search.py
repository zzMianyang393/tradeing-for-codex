from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, replace
from pathlib import Path
from typing import Iterable

from config import BacktestConfig
from rolling_window_audit import run_rolling_audit


SEARCH_WINDOWS = (180, 90, 60, 30, 14, 7)


def parse_windows(raw: str) -> tuple[int, ...]:
    windows = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not windows:
        raise ValueError("at least one window is required")
    return windows


def score_rolling_summary(summary: dict) -> float:
    profit_rate = float(summary.get("profit_rate", 0.0))
    median_return = float(summary.get("median_return_pct", 0.0))
    worst_return = float(summary.get("worst_return_pct", 0.0))
    max_drawdown = float(summary.get("max_drawdown_pct", 0.0))
    score = 0.0
    score += profit_rate * 180.0
    score += median_return * 2.0
    score += min(0.0, worst_return) * 1.8
    score -= max_drawdown * 0.65
    return round(score, 4)


def score_rolling_report(report: dict) -> tuple[float, dict[str, float]]:
    scores: dict[str, float] = {}
    total = 0.0
    weights = {
        "180": 2.4,
        "90": 1.7,
        "60": 1.1,
        "30": 1.0,
        "14": 0.65,
        "7": 0.55,
    }
    for days, payload in report.get("windows", {}).items():
        summary = payload.get("summary", {})
        score = score_rolling_summary(summary)
        if days in {"180", "90"}:
            profit_rate = float(summary.get("profit_rate", 0.0))
            median_return = float(summary.get("median_return_pct", 0.0))
            worst_return = float(summary.get("worst_return_pct", 0.0))
            if profit_rate < 0.5:
                score -= (0.5 - profit_rate) * 220.0
            if median_return < 0.0:
                score += median_return * 4.0
            if worst_return < -15.0:
                score += (worst_return + 15.0) * 2.0
        scores[days] = score
        total += score * weights.get(days, 1.0)
    return round(total, 4), scores


def candidate_stream(base: BacktestConfig, trials: int, seed: int, windows: tuple[int, ...] = SEARCH_WINDOWS) -> Iterable[BacktestConfig]:
    fixed = [
        {},
        {
            "risk_per_trade": 0.04,
            "max_margin_fraction": 0.45,
            "max_total_margin_fraction": 0.45,
            "active_symbol_limit": 4,
            "short_window_symbol_limit": 4,
            "take_profit_atr": 0.70,
            "stop_atr": 2.8,
            "trailing_atr": 1.82,
            "min_score": 2.85,
            "enabled_regimes": ("uptrend", "range"),
        },
        {
            "risk_per_trade": 0.10,
            "max_margin_fraction": 0.45,
            "max_total_margin_fraction": 0.45,
            "active_symbol_limit": 3,
            "short_window_symbol_limit": 5,
            "range_take_profit_atr": 0.65,
            "range_stop_atr": 3.2,
            "range_trailing_atr": 1.8,
            "cooldown_bars": 36,
        },
        {
            "risk_per_trade": 0.10,
            "max_margin_fraction": 0.45,
            "max_total_margin_fraction": 0.45,
            "active_symbol_limit": 3,
            "short_window_symbol_limit": 5,
            "range_take_profit_atr": 0.65,
            "range_stop_atr": 3.2,
            "range_trailing_atr": 1.8,
            "cooldown_bars": 36,
            "selector_min_avg_quote": 120_000.0,
            "selector_max_micro_noise": 0.0070,
        },
        {
            "risk_per_trade": 0.08,
            "max_margin_fraction": 0.35,
            "max_total_margin_fraction": 0.35,
            "active_symbol_limit": 3,
            "short_window_symbol_limit": 5,
            "range_take_profit_atr": 0.65,
            "range_stop_atr": 3.2,
            "range_trailing_atr": 1.8,
            "cooldown_bars": 36,
            "selector_min_avg_quote": 150_000.0,
            "selector_max_micro_noise": 0.0068,
        },
        {
            "risk_per_trade": 0.06,
            "max_margin_fraction": 0.35,
            "max_total_margin_fraction": 0.35,
            "active_symbol_limit": 5,
            "short_window_symbol_limit": 8,
            "min_score": 3.05,
            "enabled_regimes": ("range",),
        },
    ]
    common = {
        "enable_long_window_aggressive_profile": False,
        "long_window_preferred_symbols": (),
        "validation_target_returns": {},
        "windows_days": windows,
    }
    for params in fixed:
        yield replace(base, **common, **params)

    rng = random.Random(seed)
    for _ in range(max(0, trials - len(fixed))):
        risk = rng.choice([0.025, 0.04, 0.06, 0.08, 0.10, 0.13, 0.16])
        margin = rng.choice([0.25, 0.35, 0.45, 0.55, 0.65])
        limit = rng.choice([2, 3, 4, 5, 6])
        stop = rng.choice([2.0, 2.4, 2.8, 3.2, 3.6])
        range_stop = rng.choice([2.4, 2.8, 3.2, 3.6])
        yield replace(
            base,
            **common,
            risk_per_trade=risk,
            max_margin_fraction=margin,
            max_total_margin_fraction=min(margin, rng.choice([0.35, 0.45, 0.55, 0.65])),
            active_symbol_limit=limit,
            short_window_symbol_limit=rng.choice([limit, min(8, limit + 2), 10]),
            max_positions=rng.choice([1, 1, 2]),
            min_score=rng.choice([2.45, 2.65, 2.85, 3.05, 3.25]),
            take_profit_atr=rng.choice([0.55, 0.70, 0.85, 1.0]),
            stop_atr=stop,
            trailing_atr=max(0.75, stop * rng.choice([0.45, 0.55, 0.65])),
            range_take_profit_atr=rng.choice([0.55, 0.65, 0.80, 1.0]),
            range_stop_atr=range_stop,
            range_trailing_atr=max(0.75, range_stop * rng.choice([0.45, 0.55, 0.65])),
            cooldown_bars=rng.choice([12, 24, 36, 48, 72]),
            loss_cooldown_bars=rng.choice([96, 144, 240, 384]),
            symbol_edge_lookback_trades=rng.choice([1, 2, 3]),
            symbol_edge_min_win_rate=rng.choice([0.34, 0.50, 0.75, 1.0]),
            symbol_edge_pause_bars=rng.choice([96 * 7, 96 * 14, 96 * 30]),
            selector_min_avg_quote=rng.choice([0.0, 50_000.0, 100_000.0, 150_000.0, 250_000.0]),
            selector_max_micro_noise=rng.choice([0.0, 0.0062, 0.0068, 0.0072, 0.0080]),
            selector_volatility_weight=rng.choice([45.0, 70.0, 100.0, 140.0]),
            selector_noise_penalty=rng.choice([6.0, 9.0, 12.0, 18.0]),
            enabled_regimes=rng.choice([
                ("range",),
                ("transition", "range"),
                ("uptrend", "range"),
                ("downtrend", "range"),
                ("uptrend", "downtrend", "range"),
            ]),
            enable_attack_module=rng.choice([False, True]),
        )


def compact_config(config: BacktestConfig) -> dict:
    keys = (
        "risk_per_trade",
        "max_margin_fraction",
        "max_total_margin_fraction",
        "active_symbol_limit",
        "short_window_symbol_limit",
        "max_positions",
        "min_score",
        "take_profit_atr",
        "stop_atr",
        "trailing_atr",
        "range_take_profit_atr",
        "range_stop_atr",
        "range_trailing_atr",
        "cooldown_bars",
        "loss_cooldown_bars",
        "selector_min_avg_quote",
        "selector_max_micro_noise",
        "selector_volatility_weight",
        "selector_noise_penalty",
        "enabled_regimes",
        "enable_attack_module",
    )
    data = asdict(config)
    return {key: data[key] for key in keys}


def print_item(rank: int, item: dict) -> None:
    print(f"\n#{rank} score={item['score']}", flush=True)
    print(f"  config={item['config']}", flush=True)
    for days, score in item["window_scores"].items():
        summary = item["report"]["windows"][days]["summary"]
        print(
            f"  {days:>3}d score={score:>7.2f} "
            f"profitable={summary['profitable']}/{summary['available']} "
            f"median={summary['median_return_pct']:>7.2f}% "
            f"worst={summary['worst_return_pct']:>7.2f}% "
            f"dd={summary['max_drawdown_pct']:>6.2f}%",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Search configs by rolling-window consistency.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--trials", type=int, default=12)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260705)
    parser.add_argument("--stride-days", type=int, default=14)
    parser.add_argument("--max-windows", type=int, default=12)
    parser.add_argument("--windows", default="180,90,60,30,14,7")
    parser.add_argument("--out", type=Path, default=Path("reports/consistency_search.json"))
    args = parser.parse_args()

    base = BacktestConfig()
    windows = parse_windows(args.windows)
    results = []
    for idx, config in enumerate(candidate_stream(base, args.trials, args.seed, windows), start=1):
        report = run_rolling_audit(
            args.data,
            config,
            windows_days=windows,
            stride_days=args.stride_days,
            max_windows=args.max_windows,
        )
        score, window_scores = score_rolling_report(report)
        item = {
            "trial": idx,
            "score": score,
            "window_scores": window_scores,
            "config": compact_config(config),
            "report": report,
        }
        results.append(item)
        best = max(results, key=lambda candidate: candidate["score"])
        print(f"trial {idx}/{args.trials}: score={score} best={best['score']}", flush=True)

    results.sort(key=lambda item: item["score"], reverse=True)
    payload = {"results": results[: args.top]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for rank, item in enumerate(results[: args.top], start=1):
        print_item(rank, item)
    print(f"\nsaved={args.out}", flush=True)


if __name__ == "__main__":
    main()
