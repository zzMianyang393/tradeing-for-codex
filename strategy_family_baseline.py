"""Compare existing strategy families without parameter search."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import discover_symbols, load_market


def family_config(family: str, base: BacktestConfig) -> BacktestConfig:
    common = dict(
        enable_target_window_profiles=False,
        enable_attack_module=False,
        enable_continuation_module=False,
        enable_micro_momentum_module=False,
        enable_funding_module=False,
        enable_open_interest_module=False,
        enable_trade_flow_module=False,
        enable_order_book_module=False,
        enable_dynamic_strategy_router=True,
        router_blocked_reasons=(),
        router_reason_allowed_regimes={},
    )
    if family == "transition_long":
        common.update(
            router_allowed_reasons=("transition_breakout_long",),
            router_reason_allowed_regimes={"transition_breakout_long": ("transition",)},
        )
    elif family == "trend_short":
        common.update(
            router_allowed_reasons=("trend_short",),
            router_reason_allowed_regimes={"trend_short": ("downtrend",)},
        )
    elif family in {"range_revert", "range_revert_short"}:
        common.update(
            router_allowed_reasons=(
                ("range_revert_short",) if family == "range_revert_short"
                else ("range_revert_long", "range_revert_short")
            ),
            router_reason_allowed_regimes={
                "range_revert_short": ("range",),
                **({"range_revert_long": ("range",)} if family == "range_revert" else {}),
            },
        )
    elif family == "volatility_breakout":
        common.update(
            enable_volatility_breakout=True,
            router_allowed_reasons=("volatility_breakout_long", "volatility_breakout_short"),
            router_reason_allowed_regimes={
                "volatility_breakout_long": ("transition",),
                "volatility_breakout_short": ("transition",),
            },
        )
    elif family == "attack_breakout":
        common.update(
            enable_attack_module=True,
            router_allowed_reasons=("attack_breakout_long", "attack_breakout_short"),
            router_reason_allowed_regimes={
                "attack_breakout_long": ("uptrend", "transition"),
                "attack_breakout_short": ("downtrend", "transition"),
            },
        )
    else:
        raise ValueError(f"unknown family: {family}")
    return replace(base, **common)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare strategy families on fixed data and risk settings.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", type=int, default=5)
    parser.add_argument("--symbol-list", default="", help="Comma-separated symbols; overrides --symbols")
    parser.add_argument(
        "--families",
        default="transition_long,trend_short,range_revert,volatility_breakout,attack_breakout",
    )
    parser.add_argument("--out", type=Path, default=Path("reports/strategy_family_baseline.json"))
    args = parser.parse_args()

    selected = (
        {item.strip().upper() for item in args.symbol_list.split(",") if item.strip()}
        if args.symbol_list.strip()
        else set(discover_symbols(args.data)[:args.symbols]) if args.symbols > 0 else None
    )
    market = load_market(args.data, 15, symbols=selected)
    base = BacktestConfig()
    report = {"symbols": sorted(market), "windows": {}}
    for family in [item.strip() for item in args.families.split(",") if item.strip()]:
        config = family_config(family, base)
        report["windows"][family] = {}
        for days in (365, 180, 90):
            result = Backtester(config).run(market, days=days)
            report["windows"][family][str(days)] = {
                key: result.get(key)
                for key in ("return_pct", "pnl", "max_drawdown_pct", "trades", "win_rate", "by_reason", "by_regime")
            }
            print(
                f"{family:16s} {days:>3}d return={result.get('return_pct', 0):>8.3f}% "
                f"pnl={result.get('pnl', 0):>8.4f} dd={result.get('max_drawdown_pct', 0):>7.3f}% "
                f"trades={result.get('trades', 0):>4} win={result.get('win_rate', 0) * 100:>6.2f}%",
                flush=True,
            )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
