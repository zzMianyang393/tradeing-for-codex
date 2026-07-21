"""Pre-entry market-regime labels and conditional trade-performance reporting.

Labels are based on completed 4h candles and become available only after that
candle closes.  They are an audit vocabulary, not a trading signal.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Callable

from market import FeatureBar, add_features, resample_minutes
from strategy import Signal


REGIME_TREND_STRENGTH = 1.0
REGIME_HIGH_VOL_ATR_PCT = 0.03
FOUR_HOURS_MS = 4 * 60 * 60 * 1000


def label_completed_4h_bars(bars_15m: list[FeatureBar]) -> list[tuple[int, str]]:
    """Return (availability timestamp, label) pairs using only completed 4h bars."""
    raw_4h = resample_minutes(bars_15m, 240)
    featured_4h = add_features(raw_4h)
    labels: list[tuple[int, str]] = []
    for bar in featured_4h:
        if bar.ema20 > bar.ema50 > bar.ema200 and bar.trend_strength >= REGIME_TREND_STRENGTH:
            label = "趋势上行"
        elif bar.ema20 < bar.ema50 < bar.ema200 and bar.trend_strength <= -REGIME_TREND_STRENGTH:
            label = "趋势下行"
        elif bar.atr_pct >= REGIME_HIGH_VOL_ATR_PCT:
            label = "高波动转换"
        else:
            label = "震荡"
        labels.append((bar.ts + FOUR_HOURS_MS, label))
    return labels


def regime_at_entry(labels: list[tuple[int, str]], entry_ts: int) -> str:
    if not labels:
        return "样本不足"
    available_at = [item[0] for item in labels]
    index = bisect_right(available_at, entry_ts) - 1
    return labels[index][1] if index >= 0 else "样本不足"


def regime_gated_provider(
    provider: Callable[[str, list[FeatureBar], int], Signal | None],
    market: dict[str, list[FeatureBar]],
    allowed_regimes: set[str],
) -> Callable[[str, list[FeatureBar], int], Signal | None]:
    """Allow a provider to emit only when a pre-declared completed-4h label matches."""
    labels_by_symbol = {symbol: label_completed_4h_bars(bars) for symbol, bars in market.items()}

    def gated(symbol: str, bars: list[FeatureBar], index: int) -> Signal | None:
        signal = provider(symbol, bars, index)
        if signal is None or index >= len(bars):
            return signal
        regime = regime_at_entry(labels_by_symbol.get(symbol, []), bars[index].ts)
        return signal if regime in allowed_regimes else None

    return gated


def _entry_ts(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def conditional_trade_report(trades: list[dict[str, Any]], market: dict[str, list[FeatureBar]]) -> dict[str, dict[str, float | int]]:
    labels = {symbol: label_completed_4h_bars(bars) for symbol, bars in market.items()}
    buckets: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        symbol = str(trade.get("symbol", ""))
        if symbol not in labels:
            continue
        try:
            regime = regime_at_entry(labels[symbol], _entry_ts(str(trade["entry_time"])))
            buckets[regime].append(float(trade.get("pnl_pct_equity", 0.0)))
        except (KeyError, TypeError, ValueError):
            continue
    return {
        regime: {
            "trades": len(values),
            "pnl_pct_equity": round(sum(values), 6),
            "avg_pnl_pct_equity": round(mean(values), 6),
            "win_rate": round(sum(value > 0 for value in values) / len(values), 6),
        }
        for regime, values in sorted(buckets.items())
    }
