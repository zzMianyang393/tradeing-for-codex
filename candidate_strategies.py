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


def build_btc_trend_pullback_provider(market: dict[str, list[FeatureBar]]) -> CandidateProvider:
    """Buy an altcoin's completed-4h reclaim only within a BTC uptrend.

    The hypothesis is deliberately cross-market: BTC establishes the broad
    risk-on regime, while the traded altcoin must first pull back and then
    reclaim on its own completed four-hour bar.  All timestamp joins use the
    current bar only, so the provider cannot inspect a later BTC or alt bar.
    """
    btc_bars = market.get("BTC-USDT-SWAP", [])
    btc_by_timestamp = {bar.ts: index for index, bar in enumerate(btc_bars)}
    four_hour_bars = 16
    trend_lookback = four_hour_bars * 40
    pullback_bars = four_hour_bars * 3

    def provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
        if symbol == "BTC-USDT-SWAP" or idx < max(trend_lookback, pullback_bars) or idx % four_hour_bars != four_hour_bars - 1:
            return None
        btc_idx = btc_by_timestamp.get(bars[idx].ts)
        if btc_idx is None or btc_idx < trend_lookback or btc_idx % four_hour_bars != four_hour_bars - 1:
            return None

        btc_closes = [btc_bars[position].close for position in range(btc_idx - trend_lookback, btc_idx + 1, four_hour_bars)]
        if len(btc_closes) < 41:
            return None
        btc_fast = sum(btc_closes[-10:]) / 10.0
        btc_slow = sum(btc_closes[-40:]) / 40.0
        if btc_closes[-1] <= btc_slow or btc_fast <= btc_slow:
            return None

        bar = bars[idx]
        previous = bars[idx - four_hour_bars]
        pullback_start = bars[idx - pullback_bars]
        pullback = previous.close / pullback_start.close - 1.0 if pullback_start.close else 0.0
        reclaim = bar.close > previous.close and bar.close > bar.ema20
        if pullback <= -0.025 and reclaim:
            return Signal(symbol, 1, 3.2, "candidate", "candidate_btc_trend_pullback")
        return None

    return provider


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


@dataclass(frozen=True)
class RSPersistenceConfig:
    """Config for relative strength persistence strategy."""
    lookback_4h: int = 30          # 5 days of 4h bars
    rebalance_4h: int = 1          # rebalance every 4h bar
    top_n: int = 3                 # go long top N performers
    btc_trend_lookback_4h: int = 30  # BTC trend filter lookback


def build_rs_persistence_provider(
    market: dict[str, list[FeatureBar]],
    config: RSPersistenceConfig = RSPersistenceConfig(),
) -> CandidateProvider:
    """Go long altcoins with strongest5-day momentum, filtered by BTC uptrend.

    Hypothesis: crypto altcoin rotations are persistent over5-15 days.
    Capital flows from BTC into strong altcoins, creating momentum that
    persists beyond noise.  Only enter when BTC itself is in uptrend
    (positive 5-day return) to avoid chasing in bear markets.

    Differences from old relative_strength:
    - Shorter lookback (5d vs 21d) — captures recent rotation
    - Top-N only (no short leg) — concentrated long exposure
    - BTC trend filter — avoids momentum in declining market
    - 4h-bar rebalance — less noise than daily
    """
    btc_bars = market.get("BTC-USDT-SWAP", [])
    btc_by_timestamp = {bar.ts: idx for idx, bar in enumerate(btc_bars)}
    four_hour_bars = 16
    lookback = config.lookback_4h * four_hour_bars
    btc_lookback = config.btc_trend_lookback_4h * four_hour_bars
    cache: dict[int, dict[str, int]] = {}

    def directions_at(ts: int) -> dict[str, int]:
        if ts in cache:
            return cache[ts]
        # BTC trend filter: skip if BTC is declining
        btc_idx = btc_by_timestamp.get(ts)
        if btc_idx is None or btc_idx < btc_lookback:
            cache[ts] = {}
            return cache[ts]
        btc_return = btc_bars[btc_idx].close / btc_bars[btc_idx - btc_lookback].close - 1.0
        if btc_return <= 0:
            cache[ts] = {}
            return cache[ts]
        # Rank all non-BTC symbols by absolute return over lookback
        ranked: list[tuple[float, str]] = []
        for symbol, bars in market.items():
            if symbol == "BTC-USDT-SWAP":
                continue
            # Find index at this timestamp
            sym_idx = None
            for i, bar in enumerate(bars):
                if bar.ts == ts:
                    sym_idx = i
                    break
            if sym_idx is None or sym_idx < lookback:
                continue
            ret = bars[sym_idx].close / bars[sym_idx - lookback].close - 1.0
            ranked.append((ret, symbol))
        ranked.sort(reverse=True)  # highest return first
        directions: dict[str, int] = {}
        for _, symbol in ranked[:config.top_n]:
            directions[symbol] = 1  # long only
        cache[ts] = directions
        return directions

    def provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
        if symbol == "BTC-USDT-SWAP":
            return None
        if idx < lookback or idx % four_hour_bars != four_hour_bars - 1:
            return None
        direction = directions_at(bars[idx].ts).get(symbol)
        if direction is None:
            return None
        return Signal(symbol, direction, 3.1, "candidate", "candidate_rs_persistence")

    return provider


@dataclass(frozen=True)
class VolCompressionBreakoutConfig:
    """Config for volatility compression breakout strategy."""
    compression_lookback_4h: int = 360   # 60 days for ATR percentile
    breakout_lookback_4h: int = 4        # recent range (4 4h bars = 16h)
    volume_lookback_4h: int = 20         # volume average lookback
    atr_percentile_threshold: float = 25.0  # ATR must be below this percentile
    volume_multiplier: float = 1.2       # volume must be > this * average


def build_vol_compression_breakout_provider(
    market: dict[str, list[FeatureBar]],
    config: VolCompressionBreakoutConfig = VolCompressionBreakoutConfig(),
) -> CandidateProvider:
    """Buy breakout from volatility compression on completed4h bars.

    Hypothesis: when ATR compresses to extreme low, pent-up supply/demand
    imbalance leads to expansion.  The signal fires when compression is
    detected (ATR in bottom quartile) AND price breaks above the recent
    range with volume expansion.

    Key design: compression and breakout are checked on the same bar.
    The breakout lookback is short (4 bars = 16h) so the "recent range"
    is tight and breakable even during compression.
    """
    four_hour_bars = 16
    comp_lookback = config.compression_lookback_4h * four_hour_bars
    breakout_lookback = config.breakout_lookback_4h * four_hour_bars
    vol_lookback = config.volume_lookback_4h * four_hour_bars

    def provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
        if symbol == "BTC-USDT-SWAP":
            return None
        if idx < max(comp_lookback, breakout_lookback) or idx % four_hour_bars != four_hour_bars - 1:
            return None

        bar = bars[idx]

        # 1. ATR compression: current ATR below Nth percentile of lookback
        atr_values = [bars[i].atr_pct for i in range(idx - comp_lookback, idx, four_hour_bars) if i >= 0]
        if len(atr_values) < 20:
            return None
        sorted_atr = sorted(atr_values)
        percentile_idx = int(len(sorted_atr) * config.atr_percentile_threshold / 100.0)
        threshold_atr = sorted_atr[max(0, percentile_idx)]
        if bar.atr_pct > threshold_atr:
            return None

        # 2. Breakout: close above highest high of recent range (short lookback)
        recent_high = max(bars[i].high for i in range(idx - breakout_lookback, idx) if i >= 0)
        if bar.close <= recent_high:
            return None

        # 3. Volume confirmation: current volume > multiplier * average
        vol_values = [bars[i].volume_quote for i in range(idx - vol_lookback, idx, four_hour_bars) if i >= 0]
        if not vol_values:
            return None
        avg_vol = sum(vol_values) / len(vol_values)
        if avg_vol <= 0 or bar.volume_quote < avg_vol * config.volume_multiplier:
            return None

        score = 3.1 + min(bar.volume_quote / max(avg_vol, 1.0) * 0.1, 0.5)
        return Signal(symbol, 1, score, "candidate", "candidate_vol_compression_breakout")

    return provider


@dataclass(frozen=True)
class VolExhaustionReversalConfig:
    """Config for volume exhaustion reversal strategy."""
    lookback_4h: int = 120          # 20 days for volume comparison
    high_lookback_4h: int = 360     # 60 days for price high
    rsi_threshold: float = 65.0     # RSI must be above this (overbought)
    volume_ratio_threshold: float = 0.7  # current vol / avg vol must be below this


def build_vol_exhaustion_reversal_provider(
    market: dict[str, list[FeatureBar]],
    config: VolExhaustionReversalConfig = VolExhaustionReversalConfig(),
) -> CandidateProvider:
    """Short when price makes new high but volume is declining (exhaustion).

    Hypothesis: when price reaches a60-day high but20-day volume is below
    average, buying pressure is exhausted.  Combined with RSI overbought,
    this signals a high-probability short reversal.

    Distinct from old volume_price_divergence: that was15m, long+short,
    and measured price-volume correlation.  This is4h, short-only, and
    measures volume exhaustion at price extremes.
    """
    four_hour_bars = 16
    lookback = config.lookback_4h * four_hour_bars
    high_lookback = config.high_lookback_4h * four_hour_bars

    def provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
        if symbol == "BTC-USDT-SWAP":
            return None
        if idx < high_lookback or idx % four_hour_bars != four_hour_bars - 1:
            return None

        bar = bars[idx]

        # 1. Price at60-day high: close >= highest high of lookback
        highest = max(bars[i].high for i in range(idx - high_lookback, idx + 1) if i >= 0)
        if bar.close < highest * 0.99:  # within 1% of high
            return None

        # 2. Volume exhaustion: current volume below average
        vol_values = [bars[i].volume_quote for i in range(idx - lookback, idx, four_hour_bars) if i >= 0]
        if not vol_values:
            return None
        avg_vol = sum(vol_values) / len(vol_values)
        if avg_vol <= 0 or bar.volume_quote > avg_vol * config.volume_ratio_threshold:
            return None

        # 3. RSI overbought
        if bar.rsi < config.rsi_threshold:
            return None

        score = 3.1 + min((config.rsi_threshold - bar.rsi) / 30.0, 0.3)  # higher RSI = lower score (contrarian)
        return Signal(symbol, -1, score, "candidate", "candidate_vol_exhaustion_reversal")

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
