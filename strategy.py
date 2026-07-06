from __future__ import annotations

from dataclasses import dataclass

from market import FeatureBar


@dataclass(slots=True, frozen=True)
class Signal:
    symbol: str
    direction: int
    score: float
    regime: str
    reason: str


def classify_regime(bar: FeatureBar) -> str:
    if bar.ema50 > bar.ema200 and bar.trend_strength > 1.2:
        return "uptrend"
    if bar.ema50 < bar.ema200 and bar.trend_strength < -1.2:
        return "downtrend"
    if bar.atr_pct < 0.0045 or abs(bar.trend_strength) < 0.9:
        return "range"
    return "transition"


def signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if idx < 220:
        return None
    bar = bars[idx]
    prev = bars[idx - 1]
    regime = classify_regime(bar)
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    atr_pct = max(bar.atr_pct, 0.0001)
    lookback_1d = bars[max(0, idx - 96)]
    move_1d = bar.close / lookback_1d.close - 1.0 if lookback_1d.close else 0.0
    candle_body = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
    candle_range = (bar.high - bar.low) / bar.close if bar.close else 0.0

    if regime == "uptrend":
        pullback_ok = prev.close < prev.ema20 and bar.close > bar.ema20 and 44 <= bar.rsi <= 62
        breakout_ok = (
            prev.close <= prev.donchian_high
            and bar.close >= bar.donchian_high * 0.999
            and vol_ratio > 1.25
            and bar.rsi <= 68
        )
        if pullback_ok or breakout_ok:
            score = 1.55 + min(1.4, abs(bar.trend_strength) / 3.2) + min(0.55, vol_ratio / 5.0)
            return Signal(symbol, 1, score, regime, "trend_long")

    if regime == "downtrend":
        pullback_ok = prev.close > prev.ema20 and bar.close < bar.ema20 and 38 <= bar.rsi <= 56
        breakout_ok = (
            prev.close >= prev.donchian_low
            and bar.close <= bar.donchian_low * 1.001
            and vol_ratio > 1.25
            and bar.rsi >= 32
        )
        if pullback_ok or breakout_ok:
            score = 1.55 + min(1.4, abs(bar.trend_strength) / 3.2) + min(0.55, vol_ratio / 5.0)
            return Signal(symbol, -1, score, regime, "trend_short")

    if regime == "range":
        band_width = (bar.bb_upper - bar.bb_lower) / bar.close if bar.close else 0.0
        long_rsi_min = getattr(config, "range_long_rsi_min", 27.0)
        long_rsi_max = getattr(config, "range_long_rsi_max", 36.0)
        short_rsi_min = getattr(config, "range_short_rsi_min", 64.0)
        short_rsi_max = getattr(config, "range_short_rsi_max", 73.0)
        max_volume_ratio = getattr(config, "range_max_volume_ratio", 1.7)
        long_max_body = getattr(config, "range_long_max_body_pct", 1.0)
        long_max_range = getattr(config, "range_long_max_range_pct", 1.0)
        short_min_move_1d = getattr(config, "range_short_min_move_1d", -1.0)
        long_max_trend = getattr(config, "range_long_max_trend_strength", 999.0)
        short_max_trend = getattr(config, "range_short_max_trend_strength", 999.0)
        if band_width > atr_pct * 2.2:
            if (
                bar.close <= bar.bb_lower * 1.001
                and long_rsi_min <= bar.rsi <= long_rsi_max
                and vol_ratio < max_volume_ratio
                and candle_body <= long_max_body
                and candle_range <= long_max_range
                and bar.trend_strength <= long_max_trend
            ):
                score = 2.45 + min(0.7, (40 - bar.rsi) / 25.0) + min(0.35, band_width / 0.018)
                return Signal(symbol, 1, score, regime, "range_revert_long")
            if (
                bar.close >= bar.bb_upper * 0.999
                and short_rsi_min <= bar.rsi <= short_rsi_max
                and vol_ratio < max_volume_ratio
                and move_1d >= short_min_move_1d
                and bar.trend_strength <= short_max_trend
            ):
                score = 2.45 + min(0.7, (bar.rsi - 60) / 25.0) + min(0.35, band_width / 0.018)
                return Signal(symbol, -1, score, regime, "range_revert_short")

    # Transition regime: only take high-volume breakouts, keeping it selective.
    if regime == "transition" and vol_ratio > 1.4:
        transition_long_enabled = getattr(config, "transition_long_enabled", True)
        transition_short_enabled = getattr(config, "transition_short_enabled", True)
        transition_long_min_move_21d = getattr(config, "transition_long_min_move_21d", -1.0)
        lookback_21d = bars[max(0, idx - 96 * 21)]
        move_21d = bar.close / lookback_21d.close - 1.0 if lookback_21d.close else 0.0
        if (
            transition_long_enabled
            and move_21d >= transition_long_min_move_21d
            and bar.close > bar.donchian_high * 0.9995
            and bar.ema20 > bar.ema50
        ):
            return Signal(symbol, 1, 2.9 + min(0.6, vol_ratio / 6.0), regime, "transition_breakout_long")
        if transition_short_enabled and bar.close < bar.donchian_low * 1.0005 and bar.ema20 < bar.ema50:
            return Signal(symbol, -1, 2.9 + min(0.6, vol_ratio / 6.0), regime, "transition_breakout_short")

    return None


def attack_signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if idx < 260:
        return None
    bar = bars[idx]
    prev = bars[idx - 1]
    regime = classify_regime(bar)
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    atr_pct = max(bar.atr_pct, 0.0001)
    candle_range = (bar.high - bar.low) / bar.close if bar.close else 0.0
    body = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
    volume_spike = config.attack_volume_spike if config else 1.55
    range_atr = config.attack_range_atr if config else 0.95
    range_ok = candle_range >= atr_pct * range_atr

    # Momentum attack: volume-backed breakout in the direction of the 15m structure.
    breakout_enabled = getattr(config, "attack_breakout_enabled", True)
    exhaustion_enabled = getattr(config, "attack_exhaustion_enabled", True)

    if breakout_enabled and regime in ("uptrend", "transition"):
        breakout = (
            bar.close >= bar.donchian_high * 0.9988
            and prev.close < bar.donchian_high * 0.9995
            and bar.ema20 >= bar.ema50
            and vol_ratio >= volume_spike
            and range_ok
            and body >= atr_pct * 0.35
            and bar.rsi <= 72
        )
        pullback_resume = (
            prev.close < prev.ema20
            and bar.close > bar.ema20
            and bar.ema20 > bar.ema50
            and vol_ratio >= volume_spike * 0.85
            and 42 <= bar.rsi <= 64
        )
        if breakout or pullback_resume:
            score = 3.0 + min(0.9, vol_ratio / 5.0) + min(0.7, abs(bar.trend_strength) / 4.0)
            return Signal(symbol, 1, score, regime, "attack_breakout_long")

    if breakout_enabled and regime in ("downtrend", "transition"):
        breakdown = (
            bar.close <= bar.donchian_low * 1.0012
            and prev.close > bar.donchian_low * 1.0005
            and bar.ema20 <= bar.ema50
            and vol_ratio >= volume_spike
            and range_ok
            and body >= atr_pct * 0.35
            and bar.rsi >= 28
        )
        pullback_resume = (
            prev.close > prev.ema20
            and bar.close < bar.ema20
            and bar.ema20 < bar.ema50
            and vol_ratio >= volume_spike * 0.85
            and 36 <= bar.rsi <= 58
        )
        if breakdown or pullback_resume:
            score = 3.0 + min(0.9, vol_ratio / 5.0) + min(0.7, abs(bar.trend_strength) / 4.0)
            return Signal(symbol, -1, score, regime, "attack_breakout_short")

    # Exhaustion attack: only fade extremes when the broader structure is not trending hard.
    if exhaustion_enabled and regime == "range":
        band_width = (bar.bb_upper - bar.bb_lower) / bar.close if bar.close else 0.0
        if band_width > atr_pct * 2.0:
            if bar.low <= bar.bb_lower * 0.998 and bar.close > bar.bb_lower and bar.rsi <= 31 and vol_ratio <= 2.2:
                score = 3.05 + min(0.65, (34 - bar.rsi) / 18.0) + min(0.45, band_width / 0.018)
                return Signal(symbol, 1, score, regime, "attack_exhaustion_long")
            if bar.high >= bar.bb_upper * 1.002 and bar.close < bar.bb_upper and bar.rsi >= 69 and vol_ratio <= 2.2:
                score = 3.05 + min(0.65, (bar.rsi - 66) / 18.0) + min(0.45, band_width / 0.018)
                return Signal(symbol, -1, score, regime, "attack_exhaustion_short")

    return None


def continuation_signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if not getattr(config, "enable_continuation_module", False):
        return None
    if idx < 260:
        return None
    bar = bars[idx]
    prev = bars[idx - 1]
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    min_volume = getattr(config, "continuation_min_volume_ratio", 1.45)
    min_trend = getattr(config, "continuation_min_trend_strength", 1.2)
    if vol_ratio < min_volume:
        return None
    up_structure = (
        bar.ema20 > bar.ema50 > bar.ema200
        and bar.trend_strength >= min_trend
        and prev.close <= prev.donchian_high
        and bar.close >= bar.donchian_high * 0.999
        and 45 <= bar.rsi <= 72
    )
    if up_structure:
        score = 3.15 + min(0.85, vol_ratio / 5.0) + min(0.75, bar.trend_strength / 4.0)
        return Signal(symbol, 1, score, "continuation", "continuation_long")
    down_structure = (
        bar.ema20 < bar.ema50 < bar.ema200
        and bar.trend_strength <= -min_trend
        and prev.close >= prev.donchian_low
        and bar.close <= bar.donchian_low * 1.001
        and 28 <= bar.rsi <= 55
    )
    if down_structure:
        score = 3.15 + min(0.85, vol_ratio / 5.0) + min(0.75, abs(bar.trend_strength) / 4.0)
        return Signal(symbol, -1, score, "continuation", "continuation_short")
    return None


def micro_momentum_signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if not getattr(config, "enable_micro_momentum_module", False):
        return None
    if idx < 220:
        return None
    bar = bars[idx]
    prev = bars[idx - 1]
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    min_volume = getattr(config, "micro_momentum_min_volume_ratio", 1.8)
    if vol_ratio < min_volume:
        return None
    atr_pct = max(bar.atr_pct, 0.0001)
    body_pct = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
    min_body = getattr(config, "micro_momentum_min_body_atr", 0.7)
    if body_pct < atr_pct * min_body:
        return None
    candle_range = (bar.high - bar.low) / bar.close if bar.close else 0.0
    if candle_range < atr_pct * 0.9:
        return None
    bullish = (
        bar.close > bar.open
        and bar.close >= bar.donchian_high * 0.999
        and prev.close <= prev.donchian_high * 1.001
        and bar.close > bar.ema20
        and 48 <= bar.rsi <= 72
    )
    if bullish:
        score = 3.25 + min(0.8, vol_ratio / 5.0) + min(0.5, body_pct / max(atr_pct * 2.0, 0.0001))
        return Signal(symbol, 1, score, "micro_momentum", "micro_momentum_long")
    bearish = (
        bar.close < bar.open
        and bar.close <= bar.donchian_low * 1.001
        and prev.close >= prev.donchian_low * 0.999
        and bar.close < bar.ema20
        and 28 <= bar.rsi <= 52
    )
    if bearish:
        score = 3.25 + min(0.8, vol_ratio / 5.0) + min(0.5, body_pct / max(atr_pct * 2.0, 0.0001))
        return Signal(symbol, -1, score, "micro_momentum", "micro_momentum_short")
    return None


def funding_signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if not getattr(config, "enable_funding_module", False):
        return None
    if idx < 220:
        return None
    bar = bars[idx]
    funding_rate = getattr(bar, "funding_rate", None)
    if funding_rate is None:
        return None
    funding_ma = float(getattr(bar, "funding_rate_ma", funding_rate) or 0.0)
    rate = float(funding_rate)
    threshold = getattr(config, "funding_abs_rate_threshold", 0.0005)
    min_abs_ma = getattr(config, "funding_min_abs_ma", 0.0002)
    if abs(rate) < threshold or abs(funding_ma) < min_abs_ma:
        return None

    crowding_score = min(1.0, abs(rate) / max(threshold * 3.0, 0.0001))
    trend_penalty = min(0.35, abs(bar.trend_strength) / 10.0)
    score = 3.3 + crowding_score - trend_penalty
    if rate < 0 and bar.rsi <= 64:
        return Signal(symbol, 1, score, "funding", "funding_extreme_long")
    if rate > 0 and bar.rsi >= 36:
        return Signal(symbol, -1, score, "funding", "funding_extreme_short")
    return None
