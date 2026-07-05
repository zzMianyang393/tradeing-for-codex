from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, replace
from pathlib import Path

from backtester import Backtester, config_for_window
from config import BacktestConfig
from market import load_market


WINDOW_WEIGHTS = {
    7: 3.0,
    14: 2.6,
    30: 2.3,
    60: 1.8,
    90: 1.7,
    180: 1.2,
    365: 1.0,
}
MIN_TRADES = {7: 4, 14: 4, 30: 8, 60: 8, 90: 12, 180: 18, 365: 35}


def concentration_ratio(result: dict) -> float:
    positive = [max(0.0, float(trade.get("pnl", 0.0))) for trade in result.get("trades_detail", [])]
    total = sum(positive)
    if total <= 0:
        return 1.0
    return round(max(positive) / total, 4)


def score_candidate(
    results: dict[int, dict],
    baseline_pnl: dict[int, float],
    rolling_report: dict | None = None,
    max_drawdown_pct: float = 45.0,
    max_concentration: float = 0.70,
    min_rolling_profit_rate: float = 0.70,
    min_rolling_worst_return_pct: float = -35.0,
    max_rolling_drawdown_pct: float = 45.0,
) -> dict:
    score = 0.0
    warnings: list[str] = []
    metrics: dict[int, dict] = {}
    for day, result in results.items():
        if not result.get("available"):
            warnings.append(f"{day}d unavailable")
            score -= 250.0
            continue
        pnl = float(result.get("pnl", 0.0))
        drawdown = float(result.get("max_drawdown_pct", 0.0))
        trades = int(result.get("trades", 0))
        concentration = concentration_ratio(result)
        baseline = baseline_pnl.get(day, 0.0)
        weight = WINDOW_WEIGHTS.get(day, 1.0)
        improvement = pnl - baseline
        score += pnl * weight + improvement * weight * 1.4
        score -= max(0.0, drawdown - 12.0) * 0.35
        if drawdown > max_drawdown_pct:
            warnings.append(f"{day}d drawdown {drawdown:.2f}% > {max_drawdown_pct:.2f}%")
            score -= (drawdown - max_drawdown_pct) * 2.5
        min_trades = MIN_TRADES.get(day, 4)
        if trades < min_trades:
            warnings.append(f"{day}d trades {trades} < {min_trades}")
            score -= (min_trades - trades) * weight * 4.0
        if concentration > max_concentration:
            warnings.append(f"{day}d concentration {concentration:.2%} > {max_concentration:.2%}")
            score -= (concentration - max_concentration) * weight * 80.0
        if rolling_report:
            summary = rolling_report.get(str(day), {}).get("summary", {})
            profit_rate = float(summary.get("profit_rate", 1.0))
            worst_return = float(summary.get("worst_return_pct", 0.0))
            rolling_drawdown = float(summary.get("max_drawdown_pct", 0.0))
            if profit_rate < min_rolling_profit_rate:
                warnings.append(
                    f"{day}d rolling profit rate {profit_rate:.2%} < {min_rolling_profit_rate:.2%}"
                )
                score -= (min_rolling_profit_rate - profit_rate) * weight * 350.0
            if worst_return < min_rolling_worst_return_pct:
                warnings.append(
                    f"{day}d rolling worst return {worst_return:.2f}% < {min_rolling_worst_return_pct:.2f}%"
                )
                score -= (min_rolling_worst_return_pct - worst_return) * weight * 0.35
            if rolling_drawdown > max_rolling_drawdown_pct:
                warnings.append(
                    f"{day}d rolling drawdown {rolling_drawdown:.2f}% > {max_rolling_drawdown_pct:.2f}%"
                )
                score -= (rolling_drawdown - max_rolling_drawdown_pct) * weight * 1.2
        metrics[day] = {
            "pnl": round(pnl, 4),
            "baseline": round(baseline, 4),
            "improvement": round(improvement, 4),
            "drawdown": round(drawdown, 4),
            "trades": trades,
            "concentration": concentration,
        }
    return {"score": round(score, 4), "warnings": warnings, "metrics": metrics}


def parse_windows(raw: str) -> tuple[int, ...]:
    return tuple(int(part.strip()) for part in raw.split(",") if part.strip())


def load_baseline(path: Path, windows: tuple[int, ...]) -> dict[int, float]:
    if not path.exists():
        return {day: 0.0 for day in windows}
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        day: float(report.get("windows", {}).get(str(day), {}).get("pnl", 0.0))
        for day in windows
    }


def load_rolling_report(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    report = json.loads(path.read_text(encoding="utf-8"))
    return report.get("windows", {})


def candidate_stream(base: BacktestConfig, trials: int, seed: int):
    rng = random.Random(seed)
    fixed = [
        {},
        {
            "risk_per_trade": 0.39,
            "max_margin_fraction": 1.95,
            "max_total_margin_fraction": 1.65,
            "excluded_symbols": base.target_window_excluded_symbols,
            "profit_lock_equity_fraction": 999.0,
            "profit_lock_risk_multiplier": 1.0,
            "profit_lock_margin_fraction": 1.0,
            "defensive_equity_fraction": 0.0,
        },
        {
            "risk_per_trade": 0.9,
            "max_margin_fraction": 1.0,
            "max_total_margin_fraction": 1.5,
            "excluded_symbols": base.target_window_excluded_symbols,
            "profit_lock_equity_fraction": 999.0,
            "profit_lock_risk_multiplier": 1.0,
            "profit_lock_margin_fraction": 1.0,
            "defensive_equity_fraction": 0.0,
        },
        {
            "risk_per_trade": 1.2,
            "max_margin_fraction": 1.5,
            "max_total_margin_fraction": 2.0,
            "max_positions": 4,
            "active_symbol_limit": 10,
            "short_window_symbol_limit": 16,
            "min_score": 2.65,
            "excluded_symbols": ("XRP-USDT-SWAP",),
            "profit_lock_equity_fraction": 999.0,
            "profit_lock_risk_multiplier": 1.0,
            "profit_lock_margin_fraction": 1.0,
            "defensive_equity_fraction": 0.0,
        },
    ]
    for params in fixed:
        yield replace(base, **params)

    exclude_options = [
        (),
        ("XRP-USDT-SWAP",),
        ("BNB-USDT-SWAP",),
        ("SUI-USDT-SWAP",),
        base.target_window_excluded_symbols,
    ]
    for _ in range(max(0, trials - len(fixed))):
        yield replace(
            base,
            risk_per_trade=rng.choice([0.32, 0.39, 0.52, 0.65, 0.9, 1.2, 1.6]),
            max_margin_fraction=rng.choice([0.85, 1.0, 1.25, 1.5, 1.95, 2.4, 3.0]),
            max_total_margin_fraction=rng.choice([0.85, 1.0, 1.5, 1.65, 2.0, 2.4, 3.0]),
            max_positions=rng.choice([2, 3, 4, 5]),
            active_symbol_limit=rng.choice([5, 6, 8, 10, 12]),
            short_window_symbol_limit=rng.choice([5, 8, 10, 12, 16]),
            min_score=rng.choice([2.45, 2.65, 2.85, 3.05, 3.25, 3.4]),
            range_take_profit_atr=rng.choice([0.55, 0.75, 1.0, 1.25]),
            range_stop_atr=rng.choice([1.8, 2.4, 3.0]),
            range_trailing_atr=rng.choice([1.2, 1.56, 2.0]),
            cooldown_bars=rng.choice([6, 12, 24, 36]),
            loss_cooldown_bars=rng.choice([24, 48, 96, 144, 240]),
            excluded_symbols=rng.choice(exclude_options),
            profit_lock_equity_fraction=999.0,
            profit_lock_risk_multiplier=1.0,
            profit_lock_margin_fraction=1.0,
            defensive_equity_fraction=0.0,
            max_trade_loss_pct_equity=rng.choice([20.0, 35.0, 50.0]),
            enable_attack_module=rng.choice([False, True]),
            attack_min_score=rng.choice([3.8, 4.0, 4.3, 4.5]),
            attack_risk_per_trade=rng.choice([0.025, 0.05, 0.1, 0.2]),
            attack_breakout_enabled=rng.choice([False, True]),
            attack_exhaustion_enabled=True,
        )


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
        "enable_attack_module",
        "attack_min_score",
        "attack_risk_per_trade",
        "attack_breakout_enabled",
        "excluded_symbols",
        "max_trade_loss_pct_equity",
    )
    data = asdict(config)
    return {key: data[key] for key in keys}


def compact_result(result: dict) -> dict:
    keys = ("pnl", "return_pct", "win_rate", "max_drawdown_pct", "trades", "by_reason", "by_symbol")
    return {key: result[key] for key in keys if key in result}


def main() -> None:
    parser = argparse.ArgumentParser(description="Search for higher-profit configs with anti-overfit penalties.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--windows", default="7,14,30,60,90,180,365")
    parser.add_argument("--baseline", type=Path, default=Path("reports/target_window_profiles_audited.json"))
    parser.add_argument("--rolling", type=Path, default=None)
    parser.add_argument("--trials", type=int, default=24)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260705)
    parser.add_argument("--out", type=Path, default=Path("reports/profit_max_search.json"))
    args = parser.parse_args()

    windows = parse_windows(args.windows)
    base = BacktestConfig(validation_target_returns={}, validation_target_win_rate=0.0)
    baseline = load_baseline(args.baseline, windows)
    rolling = load_rolling_report(args.rolling)
    market = load_market(args.data, base.timeframe_minutes)
    symbols = tuple(sorted(market))
    top: list[dict] = []
    for idx, config in enumerate(candidate_stream(base, args.trials, args.seed), start=1):
        results = {
            day: Backtester(config_for_window(config, day, symbols)).run(market, days=day)
            for day in windows
        }
        scored = score_candidate(results, baseline, rolling_report=rolling)
        item = {
            "trial": idx,
            "score": scored["score"],
            "warnings": scored["warnings"],
            "metrics": scored["metrics"],
            "config": compact_config(config),
            "results": {str(day): compact_result(results[day]) for day in windows},
        }
        top.append(item)
        top.sort(key=lambda row: row["score"], reverse=True)
        top = top[: args.top]
        if idx == 1 or idx % 5 == 0:
            print(f"trial {idx}/{args.trials}: best={top[0]['score']}", flush=True)

    payload = {"windows": windows, "baseline": baseline, "top": top}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for rank, item in enumerate(top, start=1):
        print(f"\n#{rank} score={item['score']} trial={item['trial']}", flush=True)
        print(f"  warnings={item['warnings'][:5]}", flush=True)
        print(f"  config={item['config']}", flush=True)
        for day in windows:
            result = item["results"][str(day)]
            print(
                f"  {day:>3}d pnl={result['pnl']:>8.4f} "
                f"dd={result['max_drawdown_pct']:>6.2f}% tr={result['trades']:>3}",
                flush=True,
            )
    print(f"\nsaved={args.out}", flush=True)


if __name__ == "__main__":
    main()
