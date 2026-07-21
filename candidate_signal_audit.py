"""Audit raw candidate events before an expensive execution backtest.

This is intentionally not an optimizer.  It counts each candidate's actual
point-in-time signals in a selected universe so a zero-trade result can be
distinguished from a risk-manager or execution-layer rejection.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from candidate_strategies import LOCAL_CANDIDATE_PROVIDERS, build_btc_trend_pullback_provider, build_relative_strength_provider, build_rs_persistence_provider, build_vol_compression_breakout_provider, build_vol_exhaustion_reversal_provider
from funding_proxy_strategy import build_funding_crowding_reversal_provider, load_proxy_funding
from market import FeatureBar, discover_symbols, load_market
from unified_validation import STRATEGIES, _slice_market, signal_context_symbols


def provider_for(strategy: str, market: dict[str, list[FeatureBar]], data_dir: Path):
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
        funding_by_symbol = {}
        for symbol in market:
            path = data_dir / "external" / f"{symbol.split('-')[0]}USDT_binance_funding.csv"
            if path.exists():
                funding_by_symbol[symbol] = load_proxy_funding(path)
        return build_funding_crowding_reversal_provider(funding_by_symbol)
    return LOCAL_CANDIDATE_PROVIDERS[strategy]


def audit_signals(market: dict[str, list[FeatureBar]], strategy: str, data_dir: Path) -> dict[str, Any]:
    provider = provider_for(strategy, market, data_dir)
    by_symbol: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    first_signal: str | None = None
    last_signal: str | None = None
    for symbol, bars in market.items():
        for index, bar in enumerate(bars):
            signal = provider(symbol, bars, index)
            if signal is None:
                continue
            by_symbol[symbol] += 1
            by_reason[signal.reason] += 1
            timestamp = str(bar.ts)
            first_signal = timestamp if first_signal is None else min(first_signal, timestamp)
            last_signal = timestamp if last_signal is None else max(last_signal, timestamp)
    return {
        "strategy_id": strategy,
        "raw_signals": sum(by_symbol.values()),
        "by_symbol": dict(sorted(by_symbol.items())),
        "by_reason": dict(sorted(by_reason.items())),
        "first_signal_ts": first_signal,
        "last_signal_ts": last_signal,
    }


def _mean(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def _extension_bucket(extension_atr: float | None) -> str:
    """Bucket a directional distance from EMA20 without optimizing thresholds."""
    if extension_atr is None:
        return "ATR unavailable"
    if extension_atr <= 0:
        return "未向信号方向延伸"
    if extension_atr <= 1:
        return "0-1 ATR"
    if extension_atr <= 2:
        return "1-2 ATR"
    return ">2 ATR"


def _path_metrics(direction: int, entry: float, bars: list[FeatureBar], entry_idx: int, horizon: int) -> dict[str, float] | None:
    """Measure the executable forward path after a raw signal.

    The entry is deliberately the next bar's open.  A strategy that needs the
    completed bar's close to decide cannot also assume it was filled at that
    same close in a conservative research audit.
    """
    exit_idx = entry_idx + horizon
    if entry <= 0 or exit_idx >= len(bars):
        return None
    path = bars[entry_idx : exit_idx + 1]
    exit_price = bars[exit_idx].close
    directional_return = direction * (exit_price / entry - 1.0)
    if direction > 0:
        mfe = max(bar.high for bar in path) / entry - 1.0
        mae = min(bar.low for bar in path) / entry - 1.0
    else:
        mfe = entry / min(bar.low for bar in path) - 1.0
        mae = entry / max(bar.high for bar in path) - 1.0
    return {"return": directional_return, "mfe": mfe, "mae": mae}


def audit_entry_timing(
    market: dict[str, list[FeatureBar]],
    strategy: str,
    data_dir: Path,
    horizons: tuple[int, ...] = (4, 16, 48, 96),
    execution_delay_bars: int = 1,
) -> dict[str, Any]:
    """Audit whether actual candidate signals are late or immediately adverse.

    This is a raw-signal diagnostic, not a position-level backtest: overlapping
    events are intentionally retained, because the question is whether the
    *entry condition* is systematically extended or fragile before portfolio
    limits and cooldowns hide it.
    """
    if execution_delay_bars < 1:
        raise ValueError("execution_delay_bars must be at least one completed bar")
    provider = provider_for(strategy, market, data_dir)
    events: list[dict[str, Any]] = []
    for symbol, bars in market.items():
        for signal_idx, signal_bar in enumerate(bars):
            signal = provider(symbol, bars, signal_idx)
            entry_idx = signal_idx + execution_delay_bars
            if signal is None or entry_idx >= len(bars):
                continue
            entry_bar = bars[entry_idx]
            if entry_bar.open <= 0:
                continue
            extension_atr = (
                signal.direction * (signal_bar.close - signal_bar.ema20) / signal_bar.atr
                if signal_bar.atr > 0
                else None
            )
            pre_1d = (
                signal.direction * (signal_bar.close / bars[signal_idx - 96].close - 1.0)
                if signal_idx >= 96 and bars[signal_idx - 96].close > 0
                else None
            )
            event: dict[str, Any] = {
                "symbol": symbol,
                "direction": signal.direction,
                "extension_atr": extension_atr,
                "extension_bucket": _extension_bucket(extension_atr),
                "pre_1d_return": pre_1d,
                "signal_to_next_open_return": signal.direction * (entry_bar.open / signal_bar.close - 1.0),
                "paths": {},
            }
            for horizon in horizons:
                metrics = _path_metrics(signal.direction, entry_bar.open, bars, entry_idx, horizon)
                if metrics is not None:
                    event["paths"][str(horizon)] = metrics
            events.append(event)

    by_bucket: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_bucket.setdefault(event["extension_bucket"], []).append(event)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        report: dict[str, Any] = {
            "signals": len(items),
            "avg_extension_atr": _mean(item["extension_atr"] for item in items if item["extension_atr"] is not None),
            "avg_pre_1d_return": _mean(item["pre_1d_return"] for item in items if item["pre_1d_return"] is not None),
            "avg_signal_to_next_open_return": _mean(item["signal_to_next_open_return"] for item in items),
            "forward": {},
        }
        for horizon in horizons:
            paths = [item["paths"].get(str(horizon)) for item in items]
            complete = [path for path in paths if path is not None]
            report["forward"][f"{horizon}x15m"] = {
                "signals": len(complete),
                "avg_return": _mean(path["return"] for path in complete),
                "win_rate": _mean(1.0 if path["return"] > 0 else 0.0 for path in complete),
                "avg_mfe": _mean(path["mfe"] for path in complete),
                "avg_mae": _mean(path["mae"] for path in complete),
            }
        return report

    return {
        "strategy_id": strategy,
        "methodology": {
            "entry": f"signal after completed bar, execute next {execution_delay_bars}x15m bar open",
            "extension": "directional distance from signal close to EMA20, scaled by signal-bar ATR",
            "forward_horizons_bars": list(horizons),
            "note": "raw signals may overlap; this diagnoses entry quality rather than portfolio return",
        },
        "overall": summarize(events),
        "by_extension_bucket": {bucket: summarize(items) for bucket, items in sorted(by_bucket.items())},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit raw actual-candidate signals.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--strategy", required=True, choices=STRATEGIES)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--universe", default="alts", choices=("core", "majors", "alts", "all"))
    parser.add_argument("--out", type=Path, default=Path("reports/candidate_signal_audit.json"))
    args = parser.parse_args(argv)
    source_symbols = discover_symbols(args.data)
    majors = [symbol for symbol in ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "XRP-USDT-SWAP") if symbol in source_symbols]
    source_universes = {
        "core": [symbol for symbol in ("BTC-USDT-SWAP", "ETH-USDT-SWAP") if symbol in source_symbols],
        "majors": majors,
        "alts": [symbol for symbol in source_symbols if symbol not in majors],
        "all": list(source_symbols),
    }
    market = load_market(
        args.data,
        15,
        symbols=set(signal_context_symbols(args.strategy, source_universes[args.universe])),
    )
    trade_market = _slice_market(market, args.days, source_universes[args.universe])
    signal_market = _slice_market(market, args.days, signal_context_symbols(args.strategy, source_universes[args.universe]))
    # ``trade_market`` is still reported so the audit cannot accidentally
    # imply that a reference BTC bar is tradable in an alt-only universe.
    result = {
        "window_days": args.days,
        "universe": args.universe,
        "tradable_symbols": sorted(trade_market),
        **audit_signals(signal_market, args.strategy, args.data),
        "entry_timing": audit_entry_timing(signal_market, args.strategy, args.data),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
