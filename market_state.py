"""Prototype Market State Engine.

WARNING: This is a prototype engine for testing and validation of the state schemas
and contracts. Full strategic integration, register routing, OOS testing, and dynamic
portfolio allocation are part of subsequent tasks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from market import FeatureBar
from market_state_schema import (
    DailyState,
    H4State,
    M15State,
    MarketRegimeState,
    MarketState,
    MarketStateConfig,
    StateConflict,
    WeeklyState,
    ensure_utc,
)


def get_completed_bars(bars: list[FeatureBar], duration_ms: int, available_at_ms: float) -> list[FeatureBar]:
    """Filters bars to only those completed at or before available_at_ms.
    
    CRITICAL SEMANTIC CLARIFICATION:
    `bar.ts` represents the START time (opening timestamp) of the K-line bar.
    Therefore, the K-line completes (closes) at `bar.ts + duration_ms`.
    A bar is only available for calculation if its close time is <= available_at_ms.
    """
    return [bar for bar in bars if bar.ts + duration_ms <= available_at_ms]


def calculate_weekly_state(completed_bars: list[FeatureBar], config: MarketStateConfig) -> WeeklyState:
    """Calculates weekly market state from completed weekly bars."""
    if len(completed_bars) < config.min_bars_required.get("1w", 50):
        return WeeklyState(timeframe="1w")

    last_bar = completed_bars[-1]

    # Direction
    if last_bar.ema20 > last_bar.ema50 and last_bar.close > last_bar.ema20:
        direction = "uptrend"
    elif last_bar.ema20 < last_bar.ema50 and last_bar.close < last_bar.ema20:
        direction = "downtrend"
    elif last_bar.ema50 > 0 and abs(last_bar.ema20 - last_bar.ema50) / last_bar.ema50 < 0.01:
        direction = "transition"
    else:
        direction = "range"

    # Trend Strength
    trend_strength = getattr(last_bar, "trend_strength", 0.0)

    # Volatility State
    bb_widths = []
    for b in completed_bars[-20:]:
        if b.bb_mid > 0:
            bb_widths.append((b.bb_upper - b.bb_lower) / b.bb_mid)
    if bb_widths:
        current_w = bb_widths[-1]
        sorted_w = sorted(bb_widths)
        idx = sorted_w.index(current_w)
        pct = (idx / len(sorted_w)) * 100.0
        if pct < config.volatility_compressed_percentile:
            volatility_state = "compressed"
        elif pct > config.volatility_extreme_percentile:
            volatility_state = "extreme"
        elif pct > config.volatility_expanding_percentile:
            volatility_state = "expanding"
        else:
            volatility_state = "normal"
    else:
        volatility_state = "unknown"

    # Risk Cycle
    if direction == "downtrend" and volatility_state in ("expanding", "extreme"):
        risk_cycle = "high_risk"
    elif direction == "uptrend" and volatility_state in ("compressed", "normal"):
        risk_cycle = "low_risk"
    else:
        risk_cycle = "normal"

    return WeeklyState(
        timeframe="1w",
        direction=direction,
        trend_strength=trend_strength,
        volatility_state=volatility_state,
        risk_cycle=risk_cycle,
    )


def calculate_daily_state(completed_bars: list[FeatureBar], config: MarketStateConfig) -> DailyState:
    """Calculates daily market state from completed daily bars."""
    if len(completed_bars) < config.min_bars_required.get("1d", 200):
        return DailyState(timeframe="1d")

    last_bar = completed_bars[-1]

    # Direction
    if last_bar.ema20 > last_bar.ema200 and last_bar.close > last_bar.ema20:
        direction = "uptrend"
    elif last_bar.ema20 < last_bar.ema200 and last_bar.close < last_bar.ema20:
        direction = "downtrend"
    elif abs(last_bar.ema20 - last_bar.ema200) / last_bar.ema200 < 0.01:
        direction = "transition"
    else:
        direction = "range"

    # Trend Stage
    trend_bars = 0
    is_up = last_bar.ema20 > last_bar.ema200
    for b in reversed(completed_bars):
        if (b.ema20 > b.ema200) == is_up:
            trend_bars += 1
        else:
            break
    if trend_bars < 10:
        trend_stage = "early"
    elif trend_bars > 40 or last_bar.rsi > 70 or last_bar.rsi < 30:
        trend_stage = "exhaustion"
    else:
        trend_stage = "mature"

    # Volatility State
    bb_widths = []
    for b in completed_bars[-30:]:
        if b.bb_mid > 0:
            bb_widths.append((b.bb_upper - b.bb_lower) / b.bb_mid)
    if bb_widths:
        current_w = bb_widths[-1]
        sorted_w = sorted(bb_widths)
        idx = sorted_w.index(current_w)
        pct = (idx / len(sorted_w)) * 100.0
        if pct < config.volatility_compressed_percentile:
            volatility_state = "compressed"
        elif pct > config.volatility_extreme_percentile:
            volatility_state = "extreme"
        elif pct > config.volatility_expanding_percentile:
            volatility_state = "expanding"
        else:
            volatility_state = "normal"
    else:
        volatility_state = "unknown"

    # Structure
    if last_bar.close > last_bar.donchian_high * 0.99:
        structure = "breakout"
    elif last_bar.close < last_bar.donchian_low * 1.01:
        structure = "breakdown"
    elif direction == "uptrend" and last_bar.low <= last_bar.ema50:
        structure = "pullback"
    else:
        structure = "range"

    return DailyState(
        timeframe="1d",
        direction=direction,
        trend_stage=trend_stage,
        volatility_state=volatility_state,
        structure=structure,
    )


def calculate_h4_state(completed_bars: list[FeatureBar], config: MarketStateConfig, daily_dir: str) -> H4State:
    """Calculates 4h market state from completed 4h bars."""
    if len(completed_bars) < config.min_bars_required.get("4h", 200):
        return H4State(timeframe="4h")

    last_bar = completed_bars[-1]

    # H4 Direction
    if last_bar.ema20 > last_bar.ema200 and last_bar.close > last_bar.ema20:
        direction = "uptrend"
    elif last_bar.ema20 < last_bar.ema200 and last_bar.close < last_bar.ema20:
        direction = "downtrend"
    elif abs(last_bar.ema20 - last_bar.ema200) / last_bar.ema200 < 0.01:
        direction = "transition"
    else:
        direction = "range"

    # Volatility State
    bb_widths = []
    for b in completed_bars[-30:]:
        if b.bb_mid > 0:
            bb_widths.append((b.bb_upper - b.bb_lower) / b.bb_mid)
    if bb_widths:
        current_w = bb_widths[-1]
        sorted_w = sorted(bb_widths)
        idx = sorted_w.index(current_w)
        pct = (idx / len(sorted_w)) * 100.0
        if pct < config.volatility_compressed_percentile:
            volatility_state = "compressed"
        elif pct > config.volatility_extreme_percentile:
            volatility_state = "extreme"
        elif pct > config.volatility_expanding_percentile:
            volatility_state = "expanding"
        else:
            volatility_state = "normal"
    else:
        volatility_state = "unknown"

    # Tradable Regime
    if volatility_state == "extreme":
        tradable_regime = "no_trade"
    elif daily_dir in ("uptrend", "downtrend") and direction == daily_dir:
        tradable_regime = "trend_following"
    else:
        tradable_regime = "mean_reversion"

    # Trend Stage
    trend_bars = 0
    is_up = last_bar.ema20 > last_bar.ema200
    for b in reversed(completed_bars):
        if (b.ema20 > b.ema200) == is_up:
            trend_bars += 1
        else:
            break
    if trend_bars < 10:
        trend_stage = "early"
    elif trend_bars > 40 or last_bar.rsi > 70 or last_bar.rsi < 30:
        trend_stage = "exhaustion"
    else:
        trend_stage = "mature"

    # Breakout or Pullback
    if last_bar.close > last_bar.donchian_high * 0.99:
        breakout_or_pullback = "breakout"
    elif direction == "uptrend" and last_bar.low <= last_bar.ema50:
        breakout_or_pullback = "pullback"
    else:
        breakout_or_pullback = "none"

    return H4State(
        timeframe="4h",
        direction=direction,
        tradable_regime=tradable_regime,
        trend_stage=trend_stage,
        breakout_or_pullback=breakout_or_pullback,
        volatility_state=volatility_state,
    )


def calculate_m15_state(completed_bars: list[FeatureBar], config: MarketStateConfig) -> M15State:
    """Calculates 15m market state from completed 15m bars."""
    if len(completed_bars) < config.min_bars_required.get("15m", 30):
        return M15State(timeframe="15m")

    last_bar = completed_bars[-1]

    # Entry Context
    if last_bar.rsi < 30:
        entry_context = "oversold"
    elif last_bar.rsi > 70:
        entry_context = "overbought"
    elif last_bar.close > last_bar.donchian_high * 0.99:
        entry_context = "breakout_test"
    else:
        entry_context = "consolidation"

    # Momentum
    if last_bar.rsi > 65:
        momentum = "strong_bullish"
    elif last_bar.rsi > 50:
        momentum = "weak_bullish"
    elif last_bar.rsi > 35:
        momentum = "weak_bearish"
    else:
        momentum = "strong_bearish"

    # Local Structure
    if len(completed_bars) >= 5:
        recent = completed_bars[-5:]
        highs = [b.high for b in recent]
        lows = [b.low for b in recent]
        is_hh = all(highs[i] >= highs[i - 1] for i in range(1, len(highs)))
        is_ll = all(lows[i] <= lows[i - 1] for i in range(1, len(lows)))
        if is_hh and not is_ll:
            local_structure = "higher_high"
        elif is_ll and not is_hh:
            local_structure = "lower_low"
        else:
            local_structure = "range_bound"
    else:
        local_structure = "unknown"

    # Liquidity State
    vols = [b.volume_quote for b in completed_bars[-10:]]
    avg_vol = sum(vols) / len(vols) if vols else 0.0
    if avg_vol > 50000.0:
        liquidity_state = "normal"
    else:
        liquidity_state = "thin"

    return M15State(
        timeframe="15m",
        entry_context=entry_context,
        momentum=momentum,
        local_structure=local_structure,
        liquidity_state=liquidity_state,
    )


def detect_conflicts(
    weekly: WeeklyState, daily: DailyState, h4: H4State, m15: M15State, config: MarketStateConfig
) -> list[StateConflict]:
    """Detects directional, volatility, and momentum conflicts across cycles."""
    conflicts: list[StateConflict] = []

    # 1. Weekly vs Daily direction mismatch
    if weekly.direction != "unknown" and daily.direction != "unknown":
        if weekly.direction == "uptrend" and daily.direction == "downtrend":
            conflicts.append(
                StateConflict(
                    timeframe_a="1w",
                    timeframe_b="1d",
                    field="direction",
                    value_a="uptrend",
                    value_b="downtrend",
                    severity=config.conflict_rules.get("weekly_vs_daily_direction", "high"),
                    description="Weekly is in uptrend, but Daily is in downtrend.",
                )
            )
        elif weekly.direction == "downtrend" and daily.direction == "uptrend":
            conflicts.append(
                StateConflict(
                    timeframe_a="1w",
                    timeframe_b="1d",
                    field="direction",
                    value_a="downtrend",
                    value_b="uptrend",
                    severity=config.conflict_rules.get("weekly_vs_daily_direction", "high"),
                    description="Weekly is in downtrend, but Daily is in uptrend.",
                )
            )

    # 2. Daily direction vs 4H Tradable Regime mismatch
    if daily.direction != "unknown" and h4.tradable_regime != "unknown":
        if daily.direction == "uptrend" and h4.tradable_regime == "mean_reversion":
            conflicts.append(
                StateConflict(
                    timeframe_a="1d",
                    timeframe_b="4h",
                    field="direction_regime",
                    value_a="uptrend",
                    value_b="mean_reversion",
                    severity=config.conflict_rules.get("daily_vs_h4_direction", "medium"),
                    description="Daily direction is uptrend, but 4H regime is mean_reversion.",
                )
            )
        elif daily.direction == "downtrend" and h4.tradable_regime == "mean_reversion":
            conflicts.append(
                StateConflict(
                    timeframe_a="1d",
                    timeframe_b="4h",
                    field="direction_regime",
                    value_a="downtrend",
                    value_b="mean_reversion",
                    severity=config.conflict_rules.get("daily_vs_h4_direction", "medium"),
                    description="Daily direction is downtrend, but 4H regime is mean_reversion.",
                )
            )

    # 3. 4H Breakout vs 15M Momentum conflict
    if h4.breakout_or_pullback == "breakout" and m15.momentum in ("strong_bearish", "weak_bearish"):
        conflicts.append(
            StateConflict(
                timeframe_a="4h",
                timeframe_b="15m",
                field="breakout_momentum",
                value_a="breakout",
                value_b=m15.momentum,
                severity=config.conflict_rules.get("h4_vs_m15_direction", "medium"),
                description=f"4H is breaking out, but 15M momentum is bearish ({m15.momentum}).",
            )
        )

    # 4. Weekly Volatility compressed vs 4H Volatility extreme
    if weekly.volatility_state == "compressed" and h4.volatility_state == "extreme":
        conflicts.append(
            StateConflict(
                timeframe_a="1w",
                timeframe_b="4h",
                field="volatility_state",
                value_a="compressed",
                value_b="extreme",
                severity=config.conflict_rules.get("weekly_vs_h4_volatility", "medium"),
                description="Weekly volatility is compressed, but 4H volatility is extreme.",
            )
        )

    return conflicts


def calculate_market_state(
    symbol: str,
    weekly_bars: list[FeatureBar],
    daily_bars: list[FeatureBar],
    h4_bars: list[FeatureBar],
    m15_bars: list[FeatureBar],
    market_regime_info: dict[str, Any],
    config: MarketStateConfig,
    available_at: datetime | str,
) -> MarketState:
    """Main factory function to construct a MarketState snapshot at available_at."""
    utc_available_at = ensure_utc(available_at)
    available_at_ms = utc_available_at.timestamp() * 1000

    insufficient_data_reasons: list[str] = []

    # 1. Lookahead filter & count checks (bar.ts is K-line start time)
    w_comp = get_completed_bars(weekly_bars, 604800000, available_at_ms)
    if len(w_comp) < config.min_bars_required.get("1w", 50):
        insufficient_data_reasons.append(f"1w: Completed bars ({len(w_comp)}) < required ({config.min_bars_required.get('1w')})")

    d_comp = get_completed_bars(daily_bars, 86400000, available_at_ms)
    if len(d_comp) < config.min_bars_required.get("1d", 200):
        insufficient_data_reasons.append(f"1d: Completed bars ({len(d_comp)}) < required ({config.min_bars_required.get('1d')})")

    h4_comp = get_completed_bars(h4_bars, 14400000, available_at_ms)
    if len(h4_comp) < config.min_bars_required.get("4h", 200):
        insufficient_data_reasons.append(f"4h: Completed bars ({len(h4_comp)}) < required ({config.min_bars_required.get('4h')})")

    m15_comp = get_completed_bars(m15_bars, 900000, available_at_ms)
    if len(m15_comp) < config.min_bars_required.get("15m", 30):
        insufficient_data_reasons.append(f"15m: Completed bars ({len(m15_comp)}) < required ({config.min_bars_required.get('15m')})")

    # 2. Compute individual states
    weekly_state = calculate_weekly_state(w_comp, config)
    daily_state = calculate_daily_state(d_comp, config)
    h4_state = calculate_h4_state(h4_comp, config, daily_state.direction)
    m15_state = calculate_m15_state(m15_comp, config)

    # 3. Calculate source_bar_close_time (maximum completed bar close time)
    close_times = []
    if w_comp:
        close_times.append(w_comp[-1].ts + 604800000)
    if d_comp:
        close_times.append(d_comp[-1].ts + 86400000)
    if h4_comp:
        close_times.append(h4_comp[-1].ts + 14400000)
    if m15_comp:
        close_times.append(m15_comp[-1].ts + 900000)

    if close_times:
        source_bar_close_time = datetime.fromtimestamp(max(close_times) / 1000, tz=timezone.utc)
    else:
        source_bar_close_time = utc_available_at

    # 4. Construct MarketRegimeState
    market_regime = MarketRegimeState.from_dict(market_regime_info)

    # 5. Detect conflicts
    conflicts = detect_conflicts(weekly_state, daily_state, h4_state, m15_state, config)

    # 6. Check consistency
    has_high_or_medium_conflict = any(c.severity in ("high", "medium") for c in conflicts)
    is_consistent = (not has_high_or_medium_conflict) and (not insufficient_data_reasons)

    # 7. Confidence score calculation
    confidence = 1.0
    for c in conflicts:
        if c.severity == "high":
            confidence -= 0.3
        elif c.severity == "medium":
            confidence -= 0.15
    if insufficient_data_reasons:
        confidence -= 0.4
    confidence = max(0.0, min(1.0, confidence))

    # 8. State started at (find last daily trend transition bar, or default to epoch)
    state_started_at = datetime.fromtimestamp(0, tz=timezone.utc)
    if d_comp:
        current_dir = daily_state.direction
        transition_ts = d_comp[-1].ts + 86400000
        for b in reversed(d_comp[:-1]):
            b_dir = "unknown"
            if b.ema20 > b.ema200 and b.close > b.ema20:
                b_dir = "uptrend"
            elif b.ema20 < b.ema200 and b.close < b.ema20:
                b_dir = "downtrend"
            elif abs(b.ema20 - b.ema200) / b.ema200 < 0.01:
                b_dir = "transition"
            else:
                b_dir = "range"

            if b_dir != current_dir:
                break
            transition_ts = b.ts + 86400000
        state_started_at = datetime.fromtimestamp(transition_ts / 1000, tz=timezone.utc)

    # To satisfy validation relationships:
    # Ensure source_bar_close_time and state_started_at do not exceed available_at
    if source_bar_close_time > utc_available_at:
        source_bar_close_time = utc_available_at
    if state_started_at > utc_available_at:
        state_started_at = utc_available_at

    return MarketState(
        weekly=weekly_state,
        daily=daily_state,
        h4=h4_state,
        m15=m15_state,
        market_regime=market_regime,
        available_at=utc_available_at,
        source_bar_close_time=source_bar_close_time,
        confidence=confidence,
        state_started_at=state_started_at,
        version=config.version,
        insufficient_data_reasons=insufficient_data_reasons,
        conflicts=conflicts,
        is_consistent=is_consistent,
    )
