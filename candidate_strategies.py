"""Actual, point-in-time entry signals for research candidates.

Candidate evaluation must use these functions directly.  The older standalone
scripts counted candidate conditions but then delegated execution to the legacy
strategy router, which made differently named candidates indistinguishable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from market import FeatureBar
from strategy import Signal, classify_regime


CandidateProvider = Callable[[str, list[FeatureBar], int], Signal | None]


@dataclass(frozen=True)
class RelativeStrengthConfig:
    lookback_bars: int = 96 * 21
    rebalance_interval_bars: int = 96
    top_fraction: float = 0.20
    bottom_fraction: float = 0.20


def intraday_reversal_signal(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    if idx < 1:
        return None
    bar = bars[idx]
    previous = bars[idx - 1]
    move = bar.close / previous.close - 1.0 if previous.close else 0.0
    volume_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    if abs(move) < 0.03 or volume_ratio < 1.2 or abs(bar.trend_strength) > 1.0:
        return None
    direction = -1 if move > 0 else 1
    return Signal(symbol, direction, 3.0 + min(abs(move) * 20.0, 1.0), "candidate", "candidate_intraday_reversal")


def volume_price_divergence_signal(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    lookback = 20
    if idx < lookback:
        return None
    bar = bars[idx]
    past = bars[idx - lookback]
    price_change = bar.close / past.close - 1.0 if past.close else 0.0
    recent_volume = sum(item.volume_quote for item in bars[idx - 5 : idx + 1]) / 6.0
    past_volume = sum(item.volume_quote for item in bars[idx - lookback : idx - lookback + 6]) / 6.0
    volume_change = recent_volume / past_volume - 1.0 if past_volume else 0.0
    if abs(price_change) < 0.02 or volume_change >= -0.15:
        return None
    direction = -1 if price_change > 0 else 1
    return Signal(symbol, direction, 3.0 + min(abs(price_change) * 12.0, 1.0), "candidate", "candidate_volume_price_divergence")


def volatility_compression_signal(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    lookback = 20
    if idx < lookback:
        return None
    bar = bars[idx]
    sample = bars[idx - lookback : idx]
    average_atr = sum(item.atr_pct for item in sample) / len(sample)
    volume_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    if average_atr <= 0 or bar.atr_pct > average_atr * 0.8 or volume_ratio < 1.2:
        return None
    high = max(item.high for item in sample)
    low = min(item.low for item in sample)
    if bar.close > high * 1.001:
        return Signal(symbol, 1, 3.2 + min(volume_ratio / 4.0, 0.8), "candidate", "candidate_volatility_compression")
    if bar.close < low * 0.999:
        return Signal(symbol, -1, 3.2 + min(volume_ratio / 4.0, 0.8), "candidate", "candidate_volatility_compression")
    return None


def multi_timeframe_signal(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    """Use completed 4h-equivalent bars only; never inspect future bars."""
    lookback = 16 * 50
    if idx < lookback or idx % 16 != 15:
        return None
    bar = bars[idx]
    closes = [bars[item].close for item in range(idx - lookback, idx + 1, 16)]
    if len(closes) < 50:
        return None
    fast = sum(closes[-20:]) / 20.0
    slow = sum(closes[-50:]) / 50.0
    volume_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    if fast > slow and bar.close > bar.ema20 and volume_ratio >= 1.0:
        return Signal(symbol, 1, 3.1, "candidate", "candidate_multi_timeframe")
    if fast < slow and bar.close < bar.ema20 and volume_ratio >= 1.0:
        return Signal(symbol, -1, 3.1, "candidate", "candidate_multi_timeframe")
    return None


def volatility_regime_signal(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    if idx < 50:
        return None
    bar = bars[idx]
    average_atr = sum(item.atr_pct for item in bars[idx - 50 : idx]) / 50.0
    if average_atr <= 0:
        return None
    ratio = bar.atr_pct / average_atr
    volume_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    if ratio >= 1.3 and volume_ratio >= 1.2:
        if bar.close > bar.donchian_high * 0.999:
            return Signal(symbol, 1, 3.1, "candidate", "candidate_volatility_regime")
        if bar.close < bar.donchian_low * 1.001:
            return Signal(symbol, -1, 3.1, "candidate", "candidate_volatility_regime")
    if ratio <= 0.7:
        if bar.rsi <= 28 and bar.close <= bar.bb_lower:
            return Signal(symbol, 1, 3.0, "candidate", "candidate_volatility_regime")
        if bar.rsi >= 72 and bar.close >= bar.bb_upper:
            return Signal(symbol, -1, 3.0, "candidate", "candidate_volatility_regime")
    return None


def low_turnover_trend_signal(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    """Completed-4h Donchian breakout aligned with a medium-term trend.

    It deliberately emits at most one candidate per four-hour close and needs a
    20-bar 4h breakout.  That makes the hypothesis about persistent trends, not
    intraday noise or frequent mean reversion.
    """
    four_hour_bars = 16
    lookback = four_hour_bars * 55
    if idx < lookback or idx % four_hour_bars != four_hour_bars - 1:
        return None
    closes = [bars[position].close for position in range(idx - lookback, idx + 1, four_hour_bars)]
    if len(closes) < 56:
        return None
    current = closes[-1]
    fast = sum(closes[-10:]) / 10.0
    slow = sum(closes[-40:]) / 40.0
    prior_high = max(closes[-21:-1])
    prior_low = min(closes[-21:-1])
    if current > prior_high and fast > slow:
        return Signal(symbol, 1, 3.2, "candidate", "candidate_low_turnover_trend")
    if current < prior_low and fast < slow:
        return Signal(symbol, -1, 3.2, "candidate", "candidate_low_turnover_trend")
    return None


def post_shock_reversal_signal(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    """Low-frequency long reversal after a multi-day liquidation-like flush.

    The entry is not a generic oversold rule.  It requires a large three-day
    drawdown, expansion in traded volume and a completed four-hour recovery bar,
    which represents a specific exhaustion/reclaim hypothesis.
    """
    four_hour_bars = 16
    shock_lookback = 96 * 3
    if idx < shock_lookback or idx % four_hour_bars != four_hour_bars - 1:
        return None
    bar = bars[idx]
    prior = bars[idx - 1]
    three_day_return = bar.close / bars[idx - shock_lookback].close - 1.0
    volume_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    if (
        three_day_return <= -0.12
        and volume_ratio >= 1.5
        and bar.rsi <= 35.0
        and bar.close > prior.close
    ):
        score = 3.1 + min(abs(three_day_return) * 2.0, 0.5)
        return Signal(symbol, 1, score, "candidate", "candidate_post_shock_reversal")
    return None


def build_relative_strength_provider(
    market: dict[str, list[FeatureBar]],
    config: RelativeStrengthConfig = RelativeStrengthConfig(),
) -> CandidateProvider:
    """Create a point-in-time cross-sectional rotation provider.

    Signals are emitted only at rebalance bars and compare each eligible symbol
    against BTC using data available at that exact timestamp.
    """
    by_timestamp = {
        symbol: {bar.ts: idx for idx, bar in enumerate(bars)}
        for symbol, bars in market.items()
    }
    cache: dict[int, dict[str, int]] = {}

    def directions_at(ts: int) -> dict[str, int]:
        if ts in cache:
            return cache[ts]
        btc_bars = market.get("BTC-USDT-SWAP", [])
        btc_idx = by_timestamp.get("BTC-USDT-SWAP", {}).get(ts)
        if btc_idx is None or btc_idx < config.lookback_bars:
            cache[ts] = {}
            return cache[ts]
        btc_return = btc_bars[btc_idx].close / btc_bars[btc_idx - config.lookback_bars].close - 1.0
        ranked: list[tuple[float, str]] = []
        for current_symbol, current_bars in market.items():
            current_idx = by_timestamp[current_symbol].get(ts)
            if current_symbol == "BTC-USDT-SWAP" or current_idx is None or current_idx < config.lookback_bars:
                continue
            previous_close = current_bars[current_idx - config.lookback_bars].close
            if previous_close <= 0:
                continue
            relative_return = current_bars[current_idx].close / previous_close - 1.0 - btc_return
            ranked.append((relative_return, current_symbol))
        ranked.sort()
        count = max(1, int(len(ranked) * config.top_fraction))
        directions = {symbol: -1 for _, symbol in ranked[:count]}
        directions.update({symbol: 1 for _, symbol in ranked[-count:]})
        cache[ts] = directions
        return directions

    def provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
        if idx < config.lookback_bars or idx % config.rebalance_interval_bars != 0:
            return None
        direction = directions_at(bars[idx].ts).get(symbol)
        if direction is None:
            return None
        return Signal(symbol, direction, 3.0, "candidate", "candidate_relative_strength")

    return provider


LOCAL_CANDIDATE_PROVIDERS: dict[str, CandidateProvider] = {
    "intraday_reversal": intraday_reversal_signal,
    "volume_price_divergence": volume_price_divergence_signal,
    "volatility_compression": volatility_compression_signal,
    "multi_timeframe": multi_timeframe_signal,
    "volatility_regime": volatility_regime_signal,
    "low_turnover_trend": low_turnover_trend_signal,
    "post_shock_reversal": post_shock_reversal_signal,
}
