from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, replace
from pathlib import Path

from backtester import Backtester, config_for_window
from config import BacktestConfig, SymbolRisk
from market import load_market


def parse_windows(raw: str) -> tuple[int, ...]:
    windows = tuple(int(part.strip()) for part in raw.split(",") if part.strip())
    if not windows:
        raise ValueError("at least one window is required")
    return windows


def parse_window_targets(raw: str) -> dict[int, float]:
    targets: dict[int, float] = {}
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError("window targets must use DAYS:PNL pairs")
        days_raw, pnl_raw = item.split(":", 1)
        days = int(days_raw.strip())
        pnl = float(pnl_raw.strip())
        if days <= 0:
            raise ValueError("window days must be positive")
        targets[days] = pnl
    if not targets:
        raise ValueError("at least one target is required")
    return targets


def target_for_window(target_pnl: float | dict[int, float], days: int) -> float:
    if isinstance(target_pnl, dict):
        return float(target_pnl[days])
    return float(target_pnl)


def audit_goal_results(
    results: dict[int, dict],
    target_pnls: dict[int, float],
    max_drawdown_pct: float = 80.0,
    min_trades_by_window: dict[int, int] | None = None,
) -> dict:
    failures: list[str] = []
    passed_windows: list[int] = []
    min_trades_by_window = min_trades_by_window or {}
    for days, target in sorted(target_pnls.items()):
        result = results.get(days)
        if result is None:
            failures.append(f"{days}d missing")
            continue
        if not result.get("available", True):
            failures.append(f"{days}d unavailable")
            continue
        pnl = float(result.get("pnl", 0.0))
        drawdown = float(result.get("max_drawdown_pct", 0.0))
        trades = int(result.get("trades", 0))
        min_trades = int(min_trades_by_window.get(days, 1))
        if pnl < target:
            failures.append(f"{days}d pnl {pnl:g} < {target:g}")
        if drawdown > max_drawdown_pct:
            failures.append(f"{days}d drawdown {drawdown:.2f}% > {max_drawdown_pct:.2f}%")
        if trades < min_trades:
            failures.append(f"{days}d trades {trades} < {min_trades}")
        if pnl >= target and drawdown <= max_drawdown_pct and trades >= min_trades:
            passed_windows.append(days)
    return {
        "complete": not failures,
        "failures": failures,
        "passed_windows": passed_windows,
        "target_pnls": target_pnls,
        "max_drawdown_pct": max_drawdown_pct,
        "min_trades_by_window": min_trades_by_window,
    }


def score_goal_results(
    results: dict[int, dict],
    target_pnl: float | dict[int, float],
    min_trades_by_window: dict[int, int] | None = None,
) -> tuple[float, float, float, float]:
    min_trades_by_window = min_trades_by_window or {}
    drawdown = max(float(result.get("max_drawdown_pct", 999.0)) for result in results.values())
    gaps = [
        float(result.get("pnl", -999.0)) - target_for_window(target_pnl, days)
        for days, result in results.items()
    ]
    progress = 0.0
    for days, result in results.items():
        target = target_for_window(target_pnl, days)
        pnl = float(result.get("pnl", -999.0))
        progress += 1.0 if target <= 0 else max(0.0, min(pnl / target, 1.0))
        trades = int(result.get("trades", 0))
        min_trades = int(min_trades_by_window.get(days, 1))
        if trades < min_trades:
            progress -= (min_trades - trades) / max(min_trades, 1)
    min_gap = min(gaps)
    total_gap = sum(gaps)
    return round(progress, 4), round(min_gap, 4), round(total_gap - drawdown * 0.05, 4), round(-drawdown, 4)


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
        {
            "risk_per_trade": 1.2,
            "max_margin_fraction": 1.5,
            "max_total_margin_fraction": 2.5,
            "max_positions": 5,
            "active_symbol_limit": 12,
            "short_window_symbol_limit": 16,
            "min_score": 2.25,
            "range_take_profit_atr": 0.75,
            "range_stop_atr": 1.8,
            "range_trailing_atr": 1.2,
            "enable_attack_module": True,
            "attack_risk_per_trade": 0.25,
            "attack_max_positions": 3,
            "enable_continuation_module": True,
            "continuation_risk_per_trade": 0.32,
            "enable_micro_momentum_module": True,
            "micro_momentum_risk_per_trade": 0.18,
            "rm_max_single_position_pct": 1.5,
            "rm_max_total_position_pct": 2.5,
            "rm_min_liquidation_distance_pct": 0.005,
            "max_trade_loss_pct_equity": 35.0,
            "profit_lock_equity_fraction": 8.0,
            "profit_lock_risk_multiplier": 0.55,
            "profit_lock_margin_fraction": 0.8,
            "defensive_equity_fraction": 0.0,
            "leverage_caps": {},
        },
    ]
    for params in fixed:
        if params.get("leverage_caps") == {}:
            params = dict(params)
            params["leverage_caps"] = {
                symbol: SymbolRisk(75, min_notional=1.0)
                for symbol in base.leverage_caps
            }
        yield replace(base, **params)

    for _ in range(max(0, trials - len(fixed))):
        risk = rng.choice([0.18, 0.24, 0.32, 0.45, 0.65, 0.9, 1.2, 1.6, 2.0])
        yield replace(
            base,
            risk_per_trade=risk,
            max_margin_fraction=rng.choice([0.65, 0.85, 1.0, 1.25, 1.5, 2.0]),
            max_total_margin_fraction=rng.choice([0.55, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]),
            max_positions=rng.choice([2, 3, 4, 5, 6]),
            active_symbol_limit=rng.choice([6, 8, 10, 12]),
            short_window_symbol_limit=rng.choice([8, 10, 12, 16, 20]),
            min_score=rng.choice([2.0, 2.2, 2.45, 2.65, 2.85, 3.05, 3.25]),
            profit_lock_equity_fraction=999.0,
            profit_lock_risk_multiplier=1.0,
            profit_lock_margin_fraction=1.0,
            defensive_equity_fraction=0.0,
            max_trade_loss_pct_equity=rng.choice([20.0, 999.0]),
            rm_max_single_position_pct=rng.choice([0.8, 1.0, 1.5, 2.0]),
            rm_max_total_position_pct=rng.choice([0.8, 1.0, 1.5, 2.0, 3.0]),
            rm_min_liquidation_distance_pct=rng.choice([0.005, 0.01, 0.015]),
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
            enable_micro_momentum_module=rng.choice([False, True]),
            enable_funding_module=rng.choice([False, True]),
            enable_open_interest_module=rng.choice([False, True]),
            continuation_risk_per_trade=rng.choice([0.06, 0.10, 0.16, 0.24, 0.32]),
            continuation_min_volume_ratio=rng.choice([1.1, 1.25, 1.45, 1.7]),
            continuation_min_trend_strength=rng.choice([0.8, 1.0, 1.2, 1.5]),
            continuation_take_profit_atr=rng.choice([0.8, 1.2, 1.6, 2.0, 2.6]),
            continuation_stop_atr=rng.choice([1.4, 1.8, 2.2, 2.8]),
            continuation_trailing_atr=rng.choice([1.0, 1.4, 1.8, 2.2]),
            continuation_max_hold_bars=rng.choice([8, 12, 16, 24, 36]),
            attack_risk_per_trade=rng.choice([0.025, 0.05, 0.1, 0.2, 0.4]),
            attack_max_positions=rng.choice([1, 2, 3, 4]),
            micro_momentum_risk_per_trade=rng.choice([0.05, 0.08, 0.12, 0.18, 0.25]),
            funding_risk_per_trade=rng.choice([0.02, 0.04, 0.08, 0.12]),
            open_interest_risk_per_trade=rng.choice([0.02, 0.04, 0.08, 0.12]),
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


def restore_config_from_report(path: Path, base: BacktestConfig) -> BacktestConfig | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_config = payload.get("config")
    if not isinstance(raw_config, dict):
        return None
    return restore_config_payload(raw_config, base)


def restore_config_payload(raw_config: dict, base: BacktestConfig) -> BacktestConfig:
    allowed = {key: value for key, value in raw_config.items() if hasattr(base, key)}
    raw_caps = allowed.pop("leverage_caps", None)
    if isinstance(raw_caps, dict):
        allowed["leverage_caps"] = {
            symbol: value if isinstance(value, SymbolRisk) else SymbolRisk(**value)
            for symbol, value in raw_caps.items()
            if isinstance(value, dict) or isinstance(value, SymbolRisk)
        }
    for key, value in list(allowed.items()):
        if isinstance(getattr(base, key), tuple) and isinstance(value, list):
            allowed[key] = tuple(value)
    return replace(base, **allowed)


def restore_configs_from_report(path: Path, base: BacktestConfig) -> list[BacktestConfig]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    configs: list[BacktestConfig] = []
    raw_config = payload.get("config")
    if isinstance(raw_config, dict):
        configs.append(restore_config_payload(raw_config, base))
    for item in payload.get("top", []):
        if not isinstance(item, dict):
            continue
        raw_item_config = item.get("full_config") or item.get("config")
        if not isinstance(raw_item_config, dict):
            continue
        configs.append(restore_config_payload(raw_item_config, base))
    return configs


def mutate_seed_config(config: BacktestConfig, rng: random.Random) -> BacktestConfig:
    risk_scale = rng.choice([0.75, 0.9, 1.1, 1.25, 1.5])
    margin_scale = rng.choice([0.85, 1.0, 1.2, 1.5])
    score_shift = rng.choice([-0.25, -0.1, 0.1, 0.25])
    return replace(
        config,
        risk_per_trade=max(0.02, min(3.0, config.risk_per_trade * risk_scale)),
        max_margin_fraction=max(0.25, min(3.5, config.max_margin_fraction * margin_scale)),
        max_total_margin_fraction=max(0.25, min(3.5, config.max_total_margin_fraction * margin_scale)),
        min_score=max(1.5, min(4.5, config.min_score + score_shift)),
        range_take_profit_atr=max(0.25, min(4.0, config.range_take_profit_atr * rng.choice([0.8, 1.0, 1.2]))),
        range_stop_atr=max(0.8, min(4.0, config.range_stop_atr * rng.choice([0.8, 1.0, 1.2]))),
        rm_max_single_position_pct=max(
            config.rm_max_single_position_pct,
            rng.choice([config.rm_max_single_position_pct, 1.0, 1.5, 2.0]),
        ),
        rm_max_total_position_pct=max(
            config.rm_max_total_position_pct,
            rng.choice([config.rm_max_total_position_pct, 1.0, 1.5, 2.0, 3.0]),
        ),
    )


def seeded_candidate_stream(base: BacktestConfig, trials: int, seed: int, seed_reports: tuple[Path, ...]):
    yielded = 0
    seen: set[str] = set()
    rng = random.Random(seed)
    for path in seed_reports:
        if yielded >= trials:
            return
        for config in restore_configs_from_report(path, base):
            if yielded >= trials:
                return
            key = json.dumps(compact_config(config), sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            yielded += 1
            yield config
            if yielded >= trials:
                return
            mutated = mutate_seed_config(config, rng)
            key = json.dumps(compact_config(mutated), sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                yielded += 1
                yield mutated
    for config in candidate_stream(base, trials, seed):
        if yielded >= trials:
            return
        key = json.dumps(compact_config(config), sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        yielded += 1
        yield config


def market_feature_flags_for_configs(configs: list[BacktestConfig]) -> dict[str, bool]:
    return {
        "include_funding": any(config.enable_funding_module for config in configs),
        "include_open_interest": any(config.enable_open_interest_module for config in configs),
        "include_trade_flow": any(config.enable_trade_flow_module for config in configs),
        "include_order_book": any(config.enable_order_book_module for config in configs),
    }


def resolve_config_for_search_window(
    config: BacktestConfig,
    days: int,
    symbols: tuple[str, ...],
    profile_mode: str,
) -> BacktestConfig:
    if profile_mode == "base":
        return config
    if profile_mode == "window":
        return config_for_window(config, days, symbols)
    raise ValueError("profile_mode must be 'base' or 'window'")


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
        "enable_micro_momentum_module",
        "enable_funding_module",
        "enable_open_interest_module",
        "continuation_risk_per_trade",
        "continuation_take_profit_atr",
        "continuation_stop_atr",
        "continuation_min_volume_ratio",
        "continuation_min_trend_strength",
        "selector_min_avg_quote",
        "selector_max_micro_noise",
        "short_rebound_block_pct",
        "excluded_symbols",
        "attack_risk_per_trade",
        "micro_momentum_risk_per_trade",
        "funding_risk_per_trade",
        "open_interest_risk_per_trade",
        "rm_max_single_position_pct",
        "rm_max_total_position_pct",
        "rm_min_liquidation_distance_pct",
        "max_trade_loss_pct_equity",
    )
    data = asdict(config)
    return {key: data[key] for key in keys}


def main() -> None:
    parser = argparse.ArgumentParser(description="Search configs for absolute pnl targets.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--windows", default="60,30,14")
    parser.add_argument("--target-pnl", type=float, default=10.0)
    parser.add_argument("--target-pnls", default="")
    parser.add_argument("--max-drawdown-pct", type=float, default=80.0)
    parser.add_argument("--min-trades", default="")
    parser.add_argument("--trials", type=int, default=40)
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260705)
    parser.add_argument("--profile-mode", choices=("base", "window"), default="base")
    parser.add_argument(
        "--seed-reports",
        default="reports/sprint200u.json,reports/adaptive_365.json,reports/adaptive.json",
    )
    parser.add_argument("--out", type=Path, default=Path("reports/goal_search.json"))
    args = parser.parse_args()

    target_pnls = parse_window_targets(args.target_pnls) if args.target_pnls else {}
    min_trades_by_window = parse_window_targets(args.min_trades) if args.min_trades else {}
    windows = tuple(sorted(target_pnls)) if target_pnls else parse_windows(args.windows)
    score_target: float | dict[int, float] = target_pnls or args.target_pnl
    base = BacktestConfig(validation_target_returns={}, validation_target_win_rate=0.0)
    seed_reports = tuple(Path(part.strip()) for part in args.seed_reports.split(",") if part.strip())
    candidates = list(seeded_candidate_stream(base, args.trials, args.seed, seed_reports))
    market = load_market(args.data, base.timeframe_minutes, **market_feature_flags_for_configs(candidates))
    symbols = tuple(sorted(market))
    top: list[dict] = []
    for idx, config in enumerate(candidates, start=1):
        results = {
            days: Backtester(
                resolve_config_for_search_window(config, days, symbols, args.profile_mode)
            ).run(market, days=days)
            for days in windows
        }
        score = score_goal_results(results, score_target, min_trades_by_window)
        audit = (
            audit_goal_results(
                results,
                target_pnls,
                max_drawdown_pct=args.max_drawdown_pct,
                min_trades_by_window=min_trades_by_window,
            )
            if target_pnls
            else None
        )
        item = {
            "trial": idx,
            "score": score,
            "config": compact_config(config),
            "full_config": asdict(config),
            "results": {str(day): compact_result(results[day]) for day in windows},
            "audit": audit,
        }
        top.append(item)
        top.sort(key=lambda row: row["score"], reverse=True)
        top = top[: args.top]
        if idx == 1 or idx % 5 == 0:
            best = top[0]
            print(f"trial {idx}/{args.trials}: best={best['score']}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "windows": windows,
                "target_pnl": args.target_pnl,
                "target_pnls": target_pnls,
                "max_drawdown_pct": args.max_drawdown_pct,
                "min_trades_by_window": min_trades_by_window,
                "seed_reports": [str(path) for path in seed_reports],
                "profile_mode": args.profile_mode,
                "top": top,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
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
