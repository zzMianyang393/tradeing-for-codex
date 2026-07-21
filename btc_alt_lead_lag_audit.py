"""Pre-registered BTC-to-altcoin lead-lag event study using free OKX OHLCV.

This is intentionally an event study, not an executable strategy.  It tests
whether a liquid BTC impulse is followed by an under-reacting altcoin over the
next hour after conservative next-bar execution and round-trip costs.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from config import BacktestConfig
from market import FeatureBar, discover_symbols, load_market
from regime_validation import label_completed_4h_bars, regime_at_entry


@dataclass(frozen=True)
class LeadLagSpec:
    impulse_bars: int = 4
    forward_bars: int = 4
    cooldown_bars: int = 4
    impulse_atr_multiple: float = 2.0
    max_alt_response_fraction: float = 0.5
    volume_lookback_bars: int = 20
    volume_multiplier: float = 1.2


def _mean_or_none(values: list[float]) -> float | None:
    return mean(values) if values else None


def _summary(events: list[dict[str, Any]]) -> dict[str, float | int | None]:
    net_returns = [float(event["net_return"]) for event in events]
    gross_returns = [float(event["gross_return"]) for event in events]
    return {
        "events": len(events),
        "avg_gross_return": _mean_or_none(gross_returns),
        "avg_net_return": _mean_or_none(net_returns),
        "net_win_rate": _mean_or_none([1.0 if value > 0 else 0.0 for value in net_returns]),
        "net_profit_factor": (
            sum(value for value in net_returns if value > 0)
            / abs(sum(value for value in net_returns if value < 0))
            if any(value < 0 for value in net_returns)
            else None
        ),
    }


def _collect_events_for_alt(
    btc: list[FeatureBar],
    symbol: str,
    bars: list[FeatureBar],
    spec: LeadLagSpec,
    round_trip_cost: float,
    labels: list[tuple[int, str]],
) -> list[dict[str, Any]]:
    btc_index = {bar.ts: index for index, bar in enumerate(btc)}
    events: list[dict[str, Any]] = []
    min_index = max(spec.impulse_bars, spec.volume_lookback_bars)
    last_signal_index = -spec.cooldown_bars
    for alt_idx in range(min_index, len(bars) - spec.forward_bars - 1):
        ts = bars[alt_idx].ts
        btc_idx = btc_index.get(ts)
        if btc_idx is None or btc_idx < min_index or btc_idx + spec.forward_bars >= len(btc):
            continue
        if alt_idx - last_signal_index < spec.cooldown_bars:
            continue

        btc_bar = btc[btc_idx]
        btc_start = btc[btc_idx - spec.impulse_bars]
        alt_bar = bars[alt_idx]
        alt_start = bars[alt_idx - spec.impulse_bars]
        if btc_start.close <= 0 or alt_start.close <= 0:
            continue
        btc_impulse = btc_bar.close / btc_start.close - 1.0
        atr_threshold = spec.impulse_atr_multiple * mean(
            item.atr_pct for item in btc[btc_idx - spec.impulse_bars + 1 : btc_idx + 1]
        )
        if abs(btc_impulse) < atr_threshold:
            continue
        recent_volume = mean(item.volume_quote for item in btc[btc_idx - spec.impulse_bars + 1 : btc_idx + 1])
        baseline_volume = mean(item.volume_quote for item in btc[btc_idx - spec.volume_lookback_bars : btc_idx])
        if baseline_volume <= 0 or recent_volume < baseline_volume * spec.volume_multiplier:
            continue

        direction = 1 if btc_impulse > 0 else -1
        alt_response = alt_bar.close / alt_start.close - 1.0
        if direction * alt_response < 0 or direction * alt_response > direction * btc_impulse * spec.max_alt_response_fraction:
            continue

        entry = bars[alt_idx + 1].open
        exit_price = bars[alt_idx + 1 + spec.forward_bars].close
        if entry <= 0 or exit_price <= 0:
            continue
        gross_return = direction * (exit_price / entry - 1.0)
        events.append(
            {
                "symbol": symbol,
                "direction": "long" if direction > 0 else "short",
                "signal_ts": ts,
                "btc_impulse": btc_impulse,
                "alt_response": alt_response,
                "gross_return": gross_return,
                "net_return": gross_return - round_trip_cost,
                "market_regime": regime_at_entry(labels, bars[alt_idx + 1].ts),
            }
        )
        last_signal_index = alt_idx
    return events


def _report_for_events(events: list[dict[str, Any]], spec: LeadLagSpec, round_trip_cost: float) -> dict[str, Any]:

    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_direction: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_symbol[str(event["symbol"])].append(event)
        by_direction[str(event["direction"])].append(event)
        by_regime[str(event["market_regime"])].append(event)
    return {
        "methodology": {
            "entry": "next 15m bar open after a completed signal bar",
            "exit": "close four 15m bars after entry",
            "round_trip_cost": round_trip_cost,
            "raw_event_note": "events are de-overlapped per symbol, but this is not yet a portfolio backtest",
        },
        "spec": asdict(spec),
        "overall": _summary(events),
        "by_symbol": {symbol: _summary(items) for symbol, items in sorted(by_symbol.items())},
        "by_direction": {direction: _summary(items) for direction, items in sorted(by_direction.items())},
        "by_market_regime": {regime: _summary(items) for regime, items in sorted(by_regime.items())},
    }


def audit_btc_alt_lead_lag(
    market: dict[str, list[FeatureBar]],
    spec: LeadLagSpec = LeadLagSpec(),
    round_trip_cost: float | None = None,
) -> dict[str, Any]:
    """Evaluate the fixed lead-lag hypothesis without selecting parameters."""
    btc = market.get("BTC-USDT-SWAP", [])
    if not btc:
        return {"error": "BTC-USDT-SWAP is required"}
    if round_trip_cost is None:
        config = BacktestConfig()
        round_trip_cost = 2.0 * (config.taker_fee + config.slippage)
    labels = label_completed_4h_bars(btc)
    events = [
        event
        for symbol, bars in market.items()
        if symbol != "BTC-USDT-SWAP"
        for event in _collect_events_for_alt(btc, symbol, bars, spec, round_trip_cost, labels)
    ]
    return _report_for_events(events, spec, round_trip_cost)


def _as_of_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit pre-registered BTC-altcoin lead-lag events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--as-of", help="UTC date YYYY-MM-DD; defaults to the newest BTC bar")
    parser.add_argument("--out", type=Path, default=Path("reports/btc_alt_lead_lag_audit.json"))
    args = parser.parse_args(argv)
    symbols = discover_symbols(args.data)
    btc_market = load_market(args.data, 15, symbols={"BTC-USDT-SWAP"})
    if "BTC-USDT-SWAP" not in btc_market:
        raise SystemExit("BTC-USDT-SWAP data is required")
    btc = btc_market["BTC-USDT-SWAP"]
    end_ts = _as_of_timestamp(args.as_of) or btc[-1].ts
    start_ts = end_ts - args.days * 24 * 60 * 60 * 1000
    btc = [bar for bar in btc if start_ts <= bar.ts <= end_ts]
    labels = label_completed_4h_bars(btc)
    config = BacktestConfig()
    round_trip_cost = 2.0 * (config.taker_fee + config.slippage)
    events: list[dict[str, Any]] = []
    for symbol in symbols:
        if symbol == "BTC-USDT-SWAP":
            continue
        # Load and release one altcoin at a time; full 1m source files are large.
        alt_market = load_market(args.data, 15, symbols={symbol})
        bars = [bar for bar in alt_market.get(symbol, []) if start_ts <= bar.ts <= end_ts]
        events.extend(_collect_events_for_alt(btc, symbol, bars, LeadLagSpec(), round_trip_cost, labels))
    report = {
        "window_days": args.days,
        "as_of": args.as_of,
        **_report_for_events(events, LeadLagSpec(), round_trip_cost),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
