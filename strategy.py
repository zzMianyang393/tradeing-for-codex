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


def classify_regime(bar: FeatureBar, config=None) -> str:
    # Configurable regime thresholds
    uptrend_threshold = getattr(config, "regime_uptrend_threshold", 1.2) if config else 1.2
    downtrend_threshold = getattr(config, "regime_downtrend_threshold", -1.2) if config else -1.2
    range_strength_max = getattr(config, "regime_range_strength_max", 0.9) if config else 0.9
    range_atr_pct_max = getattr(config, "regime_range_atr_pct_max", 0.0045) if config else 0.0045

    if bar.ema50 > bar.ema200 and bar.trend_strength > uptrend_threshold:
        return "uptrend"
    if bar.ema50 < bar.ema200 and bar.trend_strength < downtrend_threshold:
        return "downtrend"
    if bar.atr_pct < range_atr_pct_max or abs(bar.trend_strength) < range_strength_max:
        return "range"
    return "transition"


def signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if idx < 220:
        return None
    bar = bars[idx]
    prev = bars[idx - 1]
    regime = classify_regime(bar, config)
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    atr_pct = max(bar.atr_pct, 0.0001)
    lookback_1d = bars[max(0, idx - 96)]
    move_1d = bar.close / lookback_1d.close - 1.0 if lookback_1d.close else 0.0
    candle_body = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
    candle_range = (bar.high - bar.low) / bar.close if bar.close else 0.0

    if regime == "uptrend":
        # Pullback bounce: tighter RSI (46-58), require volume > 1.0, trend not exhausted.
        pullback_ok = (
            prev.close < prev.ema20
            and bar.close > bar.ema20
            and 46 <= bar.rsi <= 58
            and vol_ratio >= 1.0
            and abs(move_1d) < 0.05  # not already extended
        )
        # Breakout: lower RSI ceiling (65), require stronger volume (1.35).
        breakout_ok = (
            prev.close <= prev.donchian_high
            and bar.close >= bar.donchian_high * 0.999
            and vol_ratio > 1.35
            and bar.rsi <= 65
        )
        if pullback_ok or breakout_ok:
            score = 2.0 + min(1.4, abs(bar.trend_strength) / 3.2) + min(0.55, vol_ratio / 5.0)
            return Signal(symbol, 1, score, regime, "trend_long")

    if regime == "downtrend":
        # Pullback bounce short: tighter RSI (42-54), require volume > 1.0, not extended.
        pullback_ok = (
            prev.close > prev.ema20
            and bar.close < bar.ema20
            and 42 <= bar.rsi <= 54
            and vol_ratio >= 1.0
            and abs(move_1d) < 0.05
        )
        # Breakdown: raise RSI floor (37), require stronger volume (1.35).
        breakout_ok = (
            prev.close >= prev.donchian_low
            and bar.close <= bar.donchian_low * 1.001
            and vol_ratio > 1.35
            and bar.rsi >= 37
        )
        if pullback_ok or breakout_ok:
            score = 2.0 + min(1.4, abs(bar.trend_strength) / 3.2) + min(0.55, vol_ratio / 5.0)
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
            # Long: require volume contraction (selling pressure fading), avoid hidden downtrend.
            vol_contracting = bar.volume_quote < bar.vol_sma * 0.9 if bar.vol_sma > 0 else True
            not_in_downtrend = bar.ema50 >= bar.ema200 * 0.98  # allow slight bearish but not full downtrend
            if (
                bar.close <= bar.bb_lower * 1.001
                and long_rsi_min <= bar.rsi <= long_rsi_max
                and vol_ratio < max_volume_ratio
                and candle_body <= long_max_body
                and candle_range <= long_max_range
                and bar.trend_strength <= long_max_trend
                and vol_contracting
                and not_in_downtrend
            ):
                score = 2.45 + min(0.7, (40 - bar.rsi) / 25.0) + min(0.35, band_width / 0.018)
                return Signal(symbol, 1, score, regime, "range_revert_long")
            # Short: require volume contraction (buying pressure fading), avoid hidden uptrend.
            vol_contracting_short = bar.volume_quote < bar.vol_sma * 0.9 if bar.vol_sma > 0 else True
            not_in_uptrend = bar.ema50 <= bar.ema200 * 1.02
            if (
                bar.close >= bar.bb_upper * 0.999
                and short_rsi_min <= bar.rsi <= short_rsi_max
                and vol_ratio < max_volume_ratio
                and move_1d >= short_min_move_1d
                and bar.trend_strength <= short_max_trend
                and vol_contracting_short
                and not_in_uptrend
            ):
                score = 2.45 + min(0.7, (bar.rsi - 60) / 25.0) + min(0.35, band_width / 0.018)
                return Signal(symbol, -1, score, regime, "range_revert_short")

    # Transition regime: breakout + pullback continuation + volume breakout.
    if regime == "transition":
        transition_long_enabled = getattr(config, "transition_long_enabled", True)
        transition_short_enabled = getattr(config, "transition_short_enabled", True)
        transition_long_min_move_21d = getattr(config, "transition_long_min_move_21d", -1.0)
        lookback_21d = bars[max(0, idx - 96 * 21)]
        move_21d = bar.close / lookback_21d.close - 1.0 if lookback_21d.close else 0.0
        move_ok = move_21d >= transition_long_min_move_21d

        # --- Pattern 1: Original high-volume breakout (strict) ---
        if vol_ratio > 1.4:
            if (
                transition_long_enabled
                and move_ok
                and bar.close > bar.donchian_high * 0.9995
                and bar.ema20 > bar.ema50
            ):
                return Signal(symbol, 1, 2.9 + min(0.6, vol_ratio / 6.0), regime, "transition_breakout_long")
            if (
                transition_short_enabled
                and bar.close < bar.donchian_low * 1.0005
                and bar.ema20 < bar.ema50
                and bar.rsi >= 38  # not oversold, avoid catching knife
                and bar.rsi <= 60  # not in strong bounce
                and abs(move_1d) < 0.06  # not already crashed
            ):
                return Signal(symbol, -1, 2.9 + min(0.6, vol_ratio / 6.0), regime, "transition_breakout_short")

        # --- Pattern 2: Pullback continuation long ---
        # After a breakout, price pulls back to EMA20 area and bounces back above it.
        # Tightened: require vol >= 1.3, ema50 > ema200 (medium-term uptrend), RSI 45-62.
        if transition_long_enabled and idx >= 2:
            prev_bar = bars[idx - 1]
            pullback_min_volume = getattr(config, "transition_long_pullback_min_volume_ratio", 1.3)
            pullback_rsi_min = getattr(config, "transition_long_pullback_rsi_min", 45.0)
            pullback_rsi_max = getattr(config, "transition_long_pullback_rsi_max", 62.0)
            pullback_max_move_21d_abs = getattr(config, "transition_long_pullback_max_move_21d_abs", 0.12)
            pullback_min_trend = getattr(config, "transition_long_pullback_min_trend_strength", 0.5)
            pullback_bounce = (
                prev_bar.close < prev_bar.ema20
                and bar.close > bar.ema20
                and bar.ema20 > bar.ema50
                and bar.ema50 > bar.ema200  # medium-term uptrend confirmed
                and pullback_rsi_min <= bar.rsi <= pullback_rsi_max
                and vol_ratio >= pullback_min_volume
                and move_ok
                and abs(move_21d) < pullback_max_move_21d_abs  # not extreme overheat
                and bar.trend_strength > pullback_min_trend  # minimum trend quality
            )
            if pullback_bounce:
                score = 2.9 + min(0.5, vol_ratio / 5.0) + min(0.3, abs(bar.trend_strength) / 4.0)
                return Signal(symbol, 1, score, regime, "transition_breakout_long")

        # --- Pattern 3: Volume breakout without overheat (relaxed) ---
        # Volume-backed push near donchian high, but not requiring extreme volume.
        # Tightened: vol >= 1.35, RSI <= 65, require trend_strength > 0.5.
        volume_min_ratio = getattr(config, "transition_long_volume_min_volume_ratio", 1.35)
        if transition_long_enabled and vol_ratio >= volume_min_ratio:
            volume_rsi_max = getattr(config, "transition_long_volume_rsi_max", 65.0)
            volume_min_trend = getattr(config, "transition_long_volume_min_trend_strength", 0.5)
            volume_min_body_atr = getattr(config, "transition_long_volume_min_body_atr", 0.25)
            volume_max_upper_shadow_body = getattr(config, "transition_long_volume_max_upper_shadow_body", 1.5)
            candle_body = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
            candle_range = (bar.high - bar.low) / bar.close if bar.close else 0.0
            upper_shadow = (bar.high - max(bar.open, bar.close)) / bar.close if bar.close else 0.0
            volume_breakout = (
                bar.close >= bar.donchian_high * 0.998
                and bar.ema20 > bar.ema50
                and bar.ema50 > bar.ema200  # medium-term uptrend confirmed
                and bar.rsi <= volume_rsi_max
                and bar.trend_strength > volume_min_trend  # minimum trend quality
                and candle_body >= bar.atr_pct * volume_min_body_atr  # reasonable body
                and upper_shadow < candle_body * volume_max_upper_shadow_body  # no long upper shadow rejection
                and move_ok
            )
            if volume_breakout:
                score = 2.8 + min(0.55, vol_ratio / 5.0) + min(0.35, abs(bar.trend_strength) / 4.0)
                return Signal(symbol, 1, score, regime, "transition_breakout_long")

        # --- Pattern 4: Post-breakout consolidation then re-breakout ---
        # A tight platform above EMA20 can add controlled entries without enabling weak strategy families.
        if transition_long_enabled and getattr(config, "transition_long_consolidation_enabled", False):
            lookback = int(getattr(config, "transition_long_consolidation_lookback_bars", 8))
            if idx >= lookback:
                platform = bars[idx - lookback:idx]
                platform_high = max(item.high for item in platform)
                platform_low = min(item.low for item in platform)
                platform_range_pct = (platform_high - platform_low) / bar.close if bar.close else 999.0
                platform_avg_volume = sum(item.volume_quote for item in platform) / max(len(platform), 1)
                platform_volume_ratio = platform_avg_volume / bar.vol_sma if bar.vol_sma > 0 else 1.0
                consolidation_max_range = getattr(config, "transition_long_consolidation_max_range_atr", 1.0)
                consolidation_min_volume = getattr(config, "transition_long_consolidation_min_volume_ratio", 1.15)
                consolidation_max_avg_volume = getattr(config, "transition_long_consolidation_max_avg_volume_ratio", 1.0)
                consolidation_rsi_max = getattr(config, "transition_long_consolidation_rsi_max", 64.0)
                consolidation_min_trend = getattr(config, "transition_long_consolidation_min_trend_strength", 0.5)
                consolidation_min_body_atr = getattr(config, "transition_long_consolidation_min_body_atr", 0.25)
                platform_above_ema20 = all(item.close >= item.ema20 for item in platform)
                candle_body = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
                consolidation_breakout = (
                    bar.close > platform_high * 1.001
                    and platform_range_pct <= atr_pct * consolidation_max_range
                    and platform_volume_ratio <= consolidation_max_avg_volume
                    and platform_above_ema20
                    and bar.ema20 > bar.ema50
                    and bar.ema50 > bar.ema200
                    and bar.rsi <= consolidation_rsi_max
                    and bar.trend_strength > consolidation_min_trend
                    and vol_ratio >= consolidation_min_volume
                    and candle_body >= atr_pct * consolidation_min_body_atr
                    and move_ok
                )
                if consolidation_breakout:
                    score = 2.75 + min(0.45, vol_ratio / 5.0) + min(0.35, abs(bar.trend_strength) / 4.0)
                    return Signal(symbol, 1, score, regime, "transition_breakout_long")

    return None


def attack_signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if idx < 260:
        return None
    bar = bars[idx]
    prev = bars[idx - 1]
    regime = classify_regime(bar, config)
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
            and bar.rsi <= 68  # tightened from 72
        )
        # Removed pullback_resume — it's trend continuation, not breakout.
        # Gets stopped out when trend stalls after the pullback.
        if breakout:
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
            and bar.rsi >= 32  # tightened from 28
        )
        if breakdown:
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


def open_interest_signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if not getattr(config, "enable_open_interest_module", False):
        return None
    if idx < 220:
        return None
    bar = bars[idx]
    oi_change = float(getattr(bar, "open_interest_change_pct", 0.0) or 0.0)
    min_change = getattr(config, "open_interest_min_change_pct", 0.08)
    if oi_change < min_change:
        return None
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    if vol_ratio < getattr(config, "open_interest_min_volume_ratio", 1.05):
        return None
    score = 3.25 + min(0.8, oi_change / max(min_change * 3.0, 0.0001)) + min(0.45, vol_ratio / 6.0)
    if bar.close >= bar.donchian_high * 0.999 and bar.close > bar.ema20 and bar.rsi <= 72:
        return Signal(symbol, 1, score, "open_interest", "open_interest_breakout_long")
    if bar.close <= bar.donchian_low * 1.001 and bar.close < bar.ema20 and bar.rsi >= 28:
        return Signal(symbol, -1, score, "open_interest", "open_interest_breakout_short")
    return None


def trade_flow_signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if not getattr(config, "enable_trade_flow_module", False):
        return None
    if idx < 220:
        return None
    bar = bars[idx]
    buy_quote = float(getattr(bar, "active_buy_quote", 0.0) or 0.0)
    sell_quote = float(getattr(bar, "active_sell_quote", 0.0) or 0.0)
    total_flow = buy_quote + sell_quote
    min_quote = getattr(config, "trade_flow_min_quote", 500_000.0)
    if total_flow < min_quote:
        return None
    imbalance = float(getattr(bar, "trade_flow_imbalance", 0.0) or 0.0)
    min_imbalance = getattr(config, "trade_flow_min_imbalance", 0.45)
    if abs(imbalance) < min_imbalance:
        return None

    flow_strength = min(0.75, abs(imbalance))
    flow_size = min(0.45, total_flow / max(bar.vol_sma * 4.0, 1.0))
    score = 3.25 + flow_strength + flow_size
    if imbalance > 0 and bar.close >= bar.donchian_high * 0.999 and bar.close > bar.ema20 and bar.rsi <= 72:
        return Signal(symbol, 1, score, "trade_flow", "trade_flow_breakout_long")
    if imbalance < 0 and bar.close <= bar.donchian_low * 1.001 and bar.close < bar.ema20 and bar.rsi >= 28:
        return Signal(symbol, -1, score, "trade_flow", "trade_flow_breakout_short")
    return None


def order_book_signal_for(symbol: str, bars: list[FeatureBar], idx: int, config=None) -> Signal | None:
    if not getattr(config, "enable_order_book_module", False):
        return None
    if idx < 220:
        return None
    bar = bars[idx]
    depth_imbalance = float(getattr(bar, "depth_imbalance", 0.0) or 0.0)
    spread_pct = float(getattr(bar, "order_book_spread_pct", 0.0) or 0.0)
    min_imbalance = getattr(config, "order_book_min_depth_imbalance", 0.3)
    max_spread = getattr(config, "order_book_max_spread_pct", 0.005)
    min_spread = getattr(config, "order_book_min_spread_pct", 0.0)

    if abs(depth_imbalance) < min_imbalance:
        return None
    if spread_pct > max_spread or spread_pct < min_spread:
        return None

    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    imbalance_strength = min(0.8, abs(depth_imbalance))
    spread_quality = min(0.3, 1.0 / max(spread_pct * 1000.0, 0.1))
    score = 3.15 + imbalance_strength + spread_quality

    # Positive imbalance means more bid depth, which is bullish.
    if depth_imbalance > 0 and bar.close >= bar.donchian_high * 0.999 and bar.close > bar.ema20 and bar.rsi <= 72:
        return Signal(symbol, 1, score, "order_book", "order_book_imbalance_long")
    if depth_imbalance < 0 and bar.close <= bar.donchian_low * 1.001 and bar.close < bar.ema20 and bar.rsi >= 28:
        return Signal(symbol, -1, score, "order_book", "order_book_imbalance_short")
    return None


def generate_all_signals(
    symbol: str,
    bars: list[FeatureBar],
    idx: int,
    config=None,
) -> list[Signal]:
    """Run all enabled signal generators and return matching signals."""
    signals: list[Signal] = []
    for fn in [
        signal_for,
        attack_signal_for,
        continuation_signal_for,
        micro_momentum_signal_for,
        funding_signal_for,
        open_interest_signal_for,
        trade_flow_signal_for,
        order_book_signal_for,
    ]:
        sig = fn(symbol, bars, idx, config)
        if sig is not None:
            signals.append(sig)
    return signals
