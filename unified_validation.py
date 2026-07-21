"""Honest, comparable validation for independently implemented candidates.

Every candidate supplies its own entry signal through ``candidate_strategies``.
The shared :class:`backtester.Backtester` owns execution costs, sizing, exits and
risk controls.  This separation prevents a candidate label from silently using
the legacy dynamic router instead of its stated signal logic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtester import Backtester, _common_timeline
from candidate_strategies import (
    LOCAL_CANDIDATE_PROVIDERS,
    build_btc_trend_pullback_provider,
    build_relative_strength_provider,
    build_rs_persistence_provider,
    build_vol_compression_breakout_provider,
    build_vol_exhaustion_reversal_provider,
)
from config import BacktestConfig
from funding_proxy_strategy import build_funding_crowding_reversal_provider, load_proxy_funding
from funding_rate import load_funding_rates
from regime_validation import conditional_trade_report, regime_gated_provider
from market import FeatureBar, discover_symbols, load_market


STRATEGIES = (
    "relative_strength",
    "relative_strength_persistence",
    "vol_compression_breakout",
    "vol_exhaustion_reversal",
    "multi_timeframe",
    "volatility_compression",
    "intraday_reversal",
    "volume_price_divergence",
    "volatility_regime",
    "low_turnover_trend",
    "post_shock_reversal",
    "btc_trend_pullback",
    "funding_crowding_reversal",
)
CROSS_MARKET_CONTEXT_STRATEGIES = frozenset({"relative_strength", "relative_strength_persistence", "btc_trend_pullback"})


def strategy_fingerprint(report: dict[str, Any]) -> str:
    """Stable fingerprint for entry decisions, not aggregate performance."""
    entries = [
        {
            "symbol": trade["symbol"],
            "direction": trade["direction"],
            "entry_time": trade["entry_time"],
            "reason": trade["reason"],
        }
        for trade in report.get("trades_detail", [])
    ]
    payload = json.dumps(entries, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def candidate_config(strategy: str = "") -> BacktestConfig:
    """Shared execution settings without legacy strategy routing."""
    base = replace(
        BacktestConfig(),
        enable_dynamic_strategy_router=False,
        enable_candidate_pool=False,
        enable_ml_module=False,
        enable_attack_module=False,
        enable_continuation_module=False,
        enable_micro_momentum_module=False,
        enable_funding_module=False,
        enable_open_interest_module=False,
        enable_trade_flow_module=False,
        enable_order_book_module=False,
        enable_volatility_breakout=False,
    )
    if strategy == "low_turnover_trend":
        return replace(
            base,
            risk_per_trade=0.025,
            max_positions=1,
            active_symbol_limit=2,
            short_window_symbol_limit=2,
            stop_atr=3.0,
            take_profit_atr=6.0,
            trailing_atr=3.0,
            max_hold_bars=96 * 4,
            cooldown_bars=96,
            loss_cooldown_bars=96 * 2,
            time_exit_loss_cooldown_bars=96 * 3,
            edge_lookback_trades=5,
            edge_pause_bars=96,
            symbol_edge_lookback_trades=3,
            symbol_edge_min_win_rate=0.34,
            symbol_edge_pause_bars=96,
            reason_edge_lookback_trades=5,
            reason_edge_min_win_rate=0.34,
            reason_edge_pause_bars=96,
        )
    if strategy == "post_shock_reversal":
        return replace(
            base,
            risk_per_trade=0.02,
            max_positions=1,
            active_symbol_limit=2,
            short_window_symbol_limit=2,
            stop_atr=2.5,
            take_profit_atr=4.0,
            trailing_atr=2.5,
            max_hold_bars=96 * 2,
            cooldown_bars=96 * 2,
            loss_cooldown_bars=96 * 3,
            time_exit_loss_cooldown_bars=96 * 3,
            edge_lookback_trades=5,
            edge_pause_bars=96,
            symbol_edge_lookback_trades=3,
            symbol_edge_min_win_rate=0.34,
            symbol_edge_pause_bars=96,
            reason_edge_lookback_trades=5,
            reason_edge_min_win_rate=0.34,
            reason_edge_pause_bars=96,
        )
    if strategy == "relative_strength_persistence":
        return replace(
            base,
            risk_per_trade=0.02,
            max_positions=3,
            active_symbol_limit=10,
            short_window_symbol_limit=10,
            stop_atr=2.5,
            take_profit_atr=4.0,
            trailing_atr=2.5,
            max_hold_bars=96 * 3,
            cooldown_bars=48,
            loss_cooldown_bars=96 * 2,
            time_exit_loss_cooldown_bars=96 * 2,
            min_score=3.0,
        )
    if strategy == "vol_compression_breakout":
        return replace(
            base,
            risk_per_trade=0.02,
            max_positions=2,
            active_symbol_limit=10,
            short_window_symbol_limit=10,
            stop_atr=2.5,
            take_profit_atr=4.0,
            trailing_atr=2.5,
            max_hold_bars=96 * 4,
            cooldown_bars=96,
            loss_cooldown_bars=96 * 2,
            time_exit_loss_cooldown_bars=96 * 2,
            min_score=3.0,
        )
    if strategy == "vol_exhaustion_reversal":
        return replace(
            base,
            risk_per_trade=0.02,
            max_positions=2,
            active_symbol_limit=10,
            short_window_symbol_limit=10,
            stop_atr=2.5,
            take_profit_atr=3.5,
            trailing_atr=2.0,
            max_hold_bars=96 * 3,
            cooldown_bars=96,
            loss_cooldown_bars=96 * 2,
            time_exit_loss_cooldown_bars=96 * 2,
            min_score=3.0,
        )
    if strategy == "btc_trend_pullback":
        return replace(
            base,
            risk_per_trade=0.02,
            max_positions=2,
            active_symbol_limit=4,
            short_window_symbol_limit=4,
            stop_atr=2.5,
            take_profit_atr=4.5,
            trailing_atr=2.5,
            max_hold_bars=96 * 3,
            cooldown_bars=96,
            loss_cooldown_bars=96 * 2,
            time_exit_loss_cooldown_bars=96 * 3,
        )
    if strategy == "funding_crowding_reversal":
        return replace(
            base,
            risk_per_trade=0.02,
            max_positions=1,
            active_symbol_limit=2,
            short_window_symbol_limit=2,
            stop_atr=2.5,
            take_profit_atr=3.5,
            trailing_atr=2.0,
            max_hold_bars=96,
            cooldown_bars=96,
            loss_cooldown_bars=96 * 2,
            time_exit_loss_cooldown_bars=96 * 2,
            edge_lookback_trades=5,
            edge_pause_bars=96,
            symbol_edge_lookback_trades=3,
            symbol_edge_min_win_rate=0.34,
            symbol_edge_pause_bars=96,
            reason_edge_lookback_trades=5,
            reason_edge_min_win_rate=0.34,
            reason_edge_pause_bars=96,
        )
    return base


def _slice_market(
    market: dict[str, list[FeatureBar]],
    days: int,
    symbol_universe: list[str],
    as_of_ts: int | None = None,
) -> dict[str, list[FeatureBar]]:
    timeline = _common_timeline(market, min_count_fraction=0.50)
    if not timeline:
        return {}
    end_ts = timeline[-1] if as_of_ts is None else max((ts for ts in timeline if ts <= as_of_ts), default=0)
    if not end_ts:
        return {}
    start_ts = end_ts - days * 24 * 3600 * 1000
    return {
        symbol: [bar for bar in bars if start_ts <= bar.ts <= end_ts]
        for symbol, bars in market.items()
        if symbol in symbol_universe
    }


def signal_context_symbols(strategy: str, symbol_universe: list[str]) -> list[str]:
    """Keep non-tradable reference markets available to cross-market signals."""
    symbols = set(symbol_universe)
    if strategy in CROSS_MARKET_CONTEXT_STRATEGIES:
        symbols.add("BTC-USDT-SWAP")
    return sorted(symbols)


def _provider_for(strategy: str, market: dict[str, list[FeatureBar]], data_dir: Path):
    if strategy == "relative_strength":
        return build_relative_strength_provider(market)
    if strategy == "relative_strength_persistence":
        return build_rs_persistence_provider(market)
    if strategy == "vol_compression_breakout":
        return build_vol_compression_breakout_provider(market)
    if strategy == "vol_exhaustion_reversal":
        return build_vol_exhaustion_reversal_provider(market)
    if strategy == "btc_trend_pullback":
        return build_btc_trend_pullback_provider(market)
    if strategy == "funding_crowding_reversal":
        return build_funding_crowding_reversal_provider(_annual_native_funding(market, data_dir))
    return LOCAL_CANDIDATE_PROVIDERS[strategy]


def _annual_native_funding(market: dict[str, list[FeatureBar]], data_dir: Path) -> dict[str, dict[int, float]]:
    """Use only OKX funding series that cover the whole annual claim window."""
    qualifying: dict[str, dict[int, float]] = {}
    minimum_span_ms = 365 * 24 * 60 * 60 * 1000
    for symbol in market:
        path = data_dir / f"{symbol}_funding.csv"
        rates = load_funding_rates(path)
        if len(rates) >= 2 and rates[-1].ts - rates[0].ts >= minimum_span_ms:
            qualifying[symbol] = load_proxy_funding(path)
    return qualifying


def run_backtest(
    market: dict[str, list[FeatureBar]],
    strategy: str,
    config: BacktestConfig,
    days: int,
    symbol_universe: list[str],
    data_dir: Path,
    as_of_ts: int | None = None,
    allowed_regimes: set[str] | None = None,
) -> dict[str, Any]:
    trade_market = _slice_market(market, days, symbol_universe, as_of_ts)
    trade_market = {symbol: bars for symbol, bars in trade_market.items() if bars}
    if not trade_market:
        return {"error": "no symbols"}
    signal_market = _slice_market(market, days, signal_context_symbols(strategy, symbol_universe), as_of_ts)
    provider = _provider_for(strategy, signal_market, data_dir)
    if allowed_regimes:
        provider = regime_gated_provider(provider, signal_market, allowed_regimes)
    report = Backtester(config).run(
        trade_market,
        days=days,
        signal_provider=provider,
    )
    if not report.get("available", False):
        return report
    report["strategy_id"] = strategy
    report["implementation"] = _implementation_for(strategy)
    report["allowed_market_regimes"] = sorted(allowed_regimes or ())
    report["conditional_by_market_regime"] = conditional_trade_report(report.get("trades_detail", []), signal_market)
    if strategy == "funding_crowding_reversal":
        native_funding = _annual_native_funding(signal_market, data_dir)
        report["funding_data_source"] = "okx_native_only"
        report["funding_symbols_loaded"] = sorted(native_funding)
    report["signal_fingerprint"] = strategy_fingerprint(report)
    return report


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "trades": report.get("trades", 0),
        "win_rate": report.get("win_rate", 0),
        "pnl": report.get("pnl", 0),
        "return_pct": report.get("return_pct", 0),
        "max_drawdown_pct": report.get("max_drawdown_pct", 0),
        "strategy_id": report.get("strategy_id"),
        "implementation": report.get("implementation"),
        "execution_semantics": report.get("execution_semantics"),
        "signal_fingerprint": report.get("signal_fingerprint"),
        "by_reason": report.get("by_reason", {}),
        "external_signal_audit": report.get("external_signal_audit", {}),
        "conditional_by_market_regime": report.get("conditional_by_market_regime", {}),
        "allowed_market_regimes": report.get("allowed_market_regimes", []),
        "funding_data_source": report.get("funding_data_source"),
        "funding_symbols_loaded": report.get("funding_symbols_loaded", []),
    }


def _implementation_for(strategy: str) -> str:
    if strategy == "funding_crowding_reversal":
        return "funding_proxy_strategy.funding_crowding_reversal_okx_native"
    return f"candidate_strategies.{strategy}"


def _duplicate_fingerprints(results: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, str]]:
    duplicates: list[dict[str, str]] = []
    keys = {key for report in results.values() for key in report}
    for key in sorted(keys):
        owners: dict[str, str] = {}
        for strategy, report in results.items():
            fingerprint = report.get(key, {}).get("signal_fingerprint")
            if not fingerprint or report.get(key, {}).get("trades", 0) == 0:
                continue
            previous = owners.get(fingerprint)
            if previous is not None:
                duplicates.append({"window": key, "first": previous, "duplicate": strategy})
            else:
                owners[fingerprint] = strategy
    return duplicates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate actual candidate strategy implementations.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/unified_validation.json"))
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--strategy", default="all", choices=["all", *STRATEGIES])
    parser.add_argument("--windows", default="90,180,365", help="Comma-separated windows, for example 90 or 90,180,365.")
    parser.add_argument("--universes", default="majors,alts,all", help="Comma-separated universes.")
    parser.add_argument("--as-of", default=None, help="UTC window end date YYYY-MM-DD for time-isolated validation.")
    parser.add_argument("--allowed-regimes", default="", help="Frozen comma-separated Chinese market labels used to gate entries.")
    args = parser.parse_args(argv)
    try:
        as_of_ts = (
            int(datetime.strptime(args.as_of, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
            if args.as_of else None
        )
    except ValueError:
        parser.error("--as-of must be YYYY-MM-DD")
    allowed_regimes = {item.strip() for item in args.allowed_regimes.split(",") if item.strip()}

    source_symbols = discover_symbols(args.data)
    core = [symbol for symbol in ("BTC-USDT-SWAP", "ETH-USDT-SWAP") if symbol in source_symbols]
    majors = [
        symbol for symbol in ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "XRP-USDT-SWAP")
        if symbol in source_symbols
    ]
    source_universes = {
        "core": core,
        "majors": majors,
        "alts": [symbol for symbol in source_symbols if symbol not in majors],
        "all": list(source_symbols),
    }
    requested_universes = tuple(item.strip() for item in args.universes.split(",") if item.strip())
    invalid_universes = [item for item in requested_universes if item not in source_universes]
    if invalid_universes:
        parser.error(f"unknown universes: {', '.join(invalid_universes)}")
    try:
        windows = tuple(int(item.strip()) for item in args.windows.split(",") if item.strip())
    except ValueError:
        parser.error("--windows must contain comma-separated integers")
    if not windows or any(window <= 0 for window in windows):
        parser.error("--windows must contain positive integers")
    strategies = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
    symbols_to_load: set[str] = set()
    for strategy in strategies:
        for universe_name in requested_universes:
            symbols_to_load.update(signal_context_symbols(strategy, source_universes[universe_name]))
    market = load_market(args.data, args.timeframe, symbols=symbols_to_load)
    if not market:
        print("ERROR: No market data", flush=True)
        return 1
    universes = {
        name: [symbol for symbol in source_universes[name] if symbol in market]
        for name in requested_universes
    }
    results: dict[str, dict[str, dict[str, Any]]] = {}

    for strategy in strategies:
        print(f"\nSTRATEGY: {strategy}", flush=True)
        strategy_results: dict[str, dict[str, Any]] = {}
        for universe_name, universe_symbols in universes.items():
            for days in windows:
                report = run_backtest(market, strategy, candidate_config(strategy), days, universe_symbols, args.data, as_of_ts, allowed_regimes)
                key = f"{universe_name}_{days}d"
                strategy_results[key] = _summary(report)
                print(
                    f"  {key}: trades={report.get('trades', 0)} "
                    f"pnl={report.get('pnl', 0):+.2f} ret={report.get('return_pct', 0):+.2f}%",
                    flush=True,
                )
            if 365 in windows:
                stress = replace(candidate_config(strategy), taker_fee=0.001, slippage=0.001)
                report = run_backtest(market, strategy, stress, 365, universe_symbols, args.data, as_of_ts, allowed_regimes)
                strategy_results[f"{universe_name}_365d_stress"] = _summary(report)
        results[strategy] = strategy_results

    duplicates = _duplicate_fingerprints(results)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validation_version": 2,
        "candidate_execution": "actual_external_signal_provider",
        "results": results,
        "integrity": {
            "passed": not duplicates,
            "duplicate_trade_fingerprints": duplicates,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved to {args.out}", flush=True)
    if duplicates:
        print("ERROR: duplicate candidate trade fingerprints detected", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
