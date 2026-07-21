"""Offline account fingerprint for the production-bound majors sleeve.

Uses local 15m BTC/ETH FeatureBars only. No exchange I/O.
Default start equity 10 USDT; optional capital-sensitivity up to 500.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from market import FeatureBar, load_market
from prod.majors_contract import MajorsSleeveConfig, STRATEGY_ID
from prod.policy import (
    DEFAULT_START_EQUITY_USDT,
    validate_production_bound_universe,
    validate_start_equity,
)


MarketMap = dict[str, list[FeatureBar]]


@dataclass
class _OpenPos:
    symbol: str
    direction: int  # +1 long only
    entry_idx: int
    entry_price: float
    qty: float
    notional: float
    margin: float
    stop: float
    take_profit: float
    trail: float
    entry_equity: float


def _one_way_cost_rate(config: MajorsSleeveConfig) -> float:
    return float(config.taker_fee) + float(config.slippage)


def _size_position(
    equity: float,
    entry: float,
    stop: float,
    config: MajorsSleeveConfig,
) -> tuple[float, float, float] | None:
    """Return (qty, notional, margin) or None if not tradable at this equity."""
    stop_dist = abs(entry - stop)
    if stop_dist <= 0 or entry <= 0 or equity <= 0:
        return None
    risk_budget = equity * float(config.risk_per_trade)
    qty_risk = risk_budget / stop_dist
    max_notional = equity * float(config.max_margin_fraction) * float(config.max_leverage)
    qty_cap = max_notional / entry
    qty = min(qty_risk, qty_cap)
    notional = qty * entry
    if notional < float(config.min_notional):
        return None
    margin = notional / float(config.max_leverage)
    if margin > equity * float(config.max_margin_fraction) + 1e-12:
        return None
    return qty, notional, margin


# Back-compat alias
_size_long = _size_position


def _signal_donchian_breakout(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < max(config.donchian_lookback, config.ema_slow) + 1:
        return None
    bar = bars[i]
    prev = bars[i - 1]
    window = bars[i - config.donchian_lookback : i]
    donchian_high = max(b.high for b in window)
    if bar.ema20 <= 0 or bar.ema50 <= 0 or bar.atr <= 0:
        return None
    gap = float(getattr(config, "min_ema_gap_fraction", 0.0) or 0.0)
    if bar.ema20 < bar.ema50 * (1.0 + gap):
        return None
    if prev.close <= donchian_high < bar.close:
        return 1
    return None


def _signal_donchian_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < max(config.donchian_lookback, config.ema_slow) + 1:
        return None
    bar = bars[i]
    prev = bars[i - 1]
    window = bars[i - config.donchian_lookback : i]
    donchian_low = min(b.low for b in window)
    if bar.ema20 <= 0 or bar.ema50 <= 0 or bar.atr <= 0:
        return None
    if bar.ema20 > bar.ema50:
        return None
    if prev.close >= donchian_low > bar.close:
        return -1
    return None


def _signal_htf_pullback(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Uptrend + pullback reclaim of ema20 → long."""
    slope_n = int(getattr(config, "htf_slope_bars", 16) or 16)
    pull_n = int(getattr(config, "pullback_lookback", 4) or 4)
    need = max(config.ema_slow, slope_n, pull_n) + 2
    if i < need:
        return None
    bar = bars[i]
    prev = bars[i - 1]
    if bar.ema20 <= 0 or bar.ema50 <= 0 or bar.atr <= 0:
        return None
    gap = float(getattr(config, "min_ema_gap_fraction", 0.0) or 0.0)
    if bar.ema20 < bar.ema50 * (1.0 + gap):
        return None
    if bar.close <= bar.ema50:
        return None
    ref = bars[i - slope_n]
    if bar.ema50 <= ref.ema50:
        return None
    window = bars[i - pull_n : i]
    touched = any(b.low <= b.ema20 * 1.001 for b in window if b.ema20 > 0)
    if not touched:
        return None
    if prev.close <= prev.ema20 and bar.close > bar.ema20:
        return 1
    return None


def _signal_htf_pullback_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Downtrend + bounce reject of ema20 → short."""
    slope_n = int(getattr(config, "htf_slope_bars", 16) or 16)
    pull_n = int(getattr(config, "pullback_lookback", 4) or 4)
    need = max(config.ema_slow, slope_n, pull_n) + 2
    if i < need:
        return None
    bar = bars[i]
    prev = bars[i - 1]
    if bar.ema20 <= 0 or bar.ema50 <= 0 or bar.atr <= 0:
        return None
    if bar.ema20 > bar.ema50:
        return None
    if bar.close >= bar.ema50:
        return None
    ref = bars[i - slope_n]
    if bar.ema50 >= ref.ema50:
        return None
    window = bars[i - pull_n : i]
    touched = any(b.high >= b.ema20 * 0.999 for b in window if b.ema20 > 0)
    if not touched:
        return None
    if prev.close >= prev.ema20 and bar.close < bar.ema20:
        return -1
    return None


def _signal_ema_cross_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < config.ema_slow + 2:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0:
        return None
    if prev.ema20 <= prev.ema50 and bar.ema20 > bar.ema50 and bar.close > bar.ema50:
        return 1
    return None


def _signal_ema_cross_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < config.ema_slow + 2:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0:
        return None
    if prev.ema20 >= prev.ema50 and bar.ema20 < bar.ema50 and bar.close < bar.ema50:
        return -1
    return None


def _signal_bb_mean_revert_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < 25:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0 or bar.bb_lower <= 0:
        return None
    # Only in non-strong downtrend: ema20 not far below ema50
    if bar.ema20 < bar.ema50 * 0.98:
        return None
    if prev.close < prev.bb_lower and bar.close >= bar.bb_lower:
        return 1
    return None


def _signal_bb_mean_revert_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < 25:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0 or bar.bb_upper <= 0:
        return None
    if bar.ema20 > bar.ema50 * 1.02:
        return None
    if prev.close > prev.bb_upper and bar.close <= bar.bb_upper:
        return -1
    return None


def _signal_vol_donchian_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    d = _signal_donchian_breakout(bars, i, config)
    if d != 1:
        return None
    bar = bars[i]
    if bar.vol_sma <= 0 or bar.volume_quote < bar.vol_sma:
        return None
    return 1


def _signal_rsi_trend_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Trend filter + RSI leave oversold."""
    if i < config.ema_slow + 2:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.ema20 <= bar.ema50 or bar.close <= bar.ema50 or bar.atr <= 0:
        return None
    if prev.rsi < 35.0 and bar.rsi >= 35.0:
        return 1
    return None


def _signal_rsi_trend_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < config.ema_slow + 2:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.ema20 >= bar.ema50 or bar.close >= bar.ema50 or bar.atr <= 0:
        return None
    if prev.rsi > 65.0 and bar.rsi <= 65.0:
        return -1
    return None


def _is_new_utc_day(bars: list[FeatureBar], i: int) -> bool:
    if i < 1:
        return False
    return bars[i].time[:10] != bars[i - 1].time[:10]


def _bars_per_day(config: MajorsSleeveConfig) -> int:
    """Approximate 15m bars in a day; 1 for native daily."""
    tf = int(getattr(config, "timeframe_minutes", 15) or 15)
    return max(1, 1440 // tf)


def _signal_daily_breakout_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Sparse: only first bar of UTC day; close breaks prior ~1d high in uptrend."""
    bpd = _bars_per_day(config)
    if bpd > 1 and not _is_new_utc_day(bars, i):
        return None
    look = max(1, bpd)  # prior day range on 15m; prior bar on daily
    if bpd == 1:
        look = 5  # prior week high on native daily
    if i < look + 5:
        return None
    bar = bars[i]
    if bar.atr <= 0 or bar.ema20 <= bar.ema50 or bar.close <= bar.ema50:
        return None
    prior_high = max(b.high for b in bars[i - look : i])
    if bar.close > prior_high:
        return 1
    return None


def _signal_daily_breakout_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    bpd = _bars_per_day(config)
    if bpd > 1 and not _is_new_utc_day(bars, i):
        return None
    look = max(1, bpd)
    if bpd == 1:
        look = 5
    if i < look + 5:
        return None
    bar = bars[i]
    if bar.atr <= 0 or bar.ema20 >= bar.ema50 or bar.close >= bar.ema50:
        return None
    prior_low = min(b.low for b in bars[i - look : i])
    if bar.close < prior_low:
        return -1
    return None


def _signal_slow_ema_cross_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """ema50 cross above ema200 — low turnover."""
    if i < 210:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0 or bar.ema200 <= 0:
        return None
    if prev.ema50 <= prev.ema200 and bar.ema50 > bar.ema200 and bar.close > bar.ema200:
        return 1
    return None


def _signal_slow_ema_cross_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < 210:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0 or bar.ema200 <= 0:
        return None
    if prev.ema50 >= prev.ema200 and bar.ema50 < bar.ema200 and bar.close < bar.ema200:
        return -1
    return None


def _signal_atr_squeeze_breakout_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """ATR compression then break prior 20-bar high."""
    look = 64
    brk = 20
    if i < look + brk + 2:
        return None
    bar = bars[i]
    if bar.atr <= 0 or bar.atr_pct <= 0:
        return None
    window = bars[i - look : i]
    atrs = sorted(b.atr_pct for b in window if b.atr_pct > 0)
    if len(atrs) < 10:
        return None
    # bottom quintile compression
    thr = atrs[max(0, len(atrs) // 5)]
    if bar.atr_pct > thr:
        return None
    prior_high = max(b.high for b in bars[i - brk : i])
    if bar.close > prior_high and bar.ema20 >= bar.ema50:
        return 1
    return None


def _signal_atr_squeeze_breakout_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    look = 64
    brk = 20
    if i < look + brk + 2:
        return None
    bar = bars[i]
    if bar.atr <= 0 or bar.atr_pct <= 0:
        return None
    window = bars[i - look : i]
    atrs = sorted(b.atr_pct for b in window if b.atr_pct > 0)
    if len(atrs) < 10:
        return None
    thr = atrs[max(0, len(atrs) // 5)]
    if bar.atr_pct > thr:
        return None
    prior_low = min(b.low for b in bars[i - brk : i])
    if bar.close < prior_low and bar.ema20 <= bar.ema50:
        return -1
    return None


def _signal_multi_day_momentum_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Sparse daily: 5d momentum + rising ema50."""
    bpd = _bars_per_day(config)
    if bpd > 1 and not _is_new_utc_day(bars, i):
        return None
    n = bpd * 5
    if i < n + 5:
        return None
    bar = bars[i]
    if bar.atr <= 0:
        return None
    ref = bars[i - n]
    day_ago = bars[i - bpd]
    if bar.close > ref.close and bar.ema50 > day_ago.ema50 and bar.close > bar.ema50:
        return 1
    return None


def _signal_multi_day_momentum_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    bpd = _bars_per_day(config)
    if bpd > 1 and not _is_new_utc_day(bars, i):
        return None
    n = bpd * 5
    if i < n + 5:
        return None
    bar = bars[i]
    if bar.atr <= 0:
        return None
    ref = bars[i - n]
    day_ago = bars[i - bpd]
    if bar.close < ref.close and bar.ema50 < day_ago.ema50 and bar.close < bar.ema50:
        return -1
    return None


def _signal_4h_close_trend_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Only on 4h boundaries (every 16th 15m bar index pattern via clock)."""
    # 15m bars: HH:00,15,30,45 — treat :00 of hours divisible by 4 as 4h close proxy
    try:
        hh = int(bars[i].time[11:13])
        mm = int(bars[i].time[14:16])
    except (ValueError, IndexError):
        return None
    if mm != 0 or hh % 4 != 0:
        return None
    if i < 1:
        return None
    # only once when we step onto this bar (prev not same boundary)
    try:
        ph = int(bars[i - 1].time[11:13])
        pm = int(bars[i - 1].time[14:16])
        if pm == 0 and ph % 4 == 0:
            return None
    except (ValueError, IndexError):
        pass
    if i < 50:
        return None
    bar = bars[i]
    if bar.atr <= 0 or bar.ema20 <= bar.ema50 or bar.close <= bar.ema50:
        return None
    # break last 16 bars high
    prior_high = max(b.high for b in bars[i - 16 : i])
    if bar.close > prior_high:
        return 1
    return None


def _signal_4h_close_trend_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    try:
        hh = int(bars[i].time[11:13])
        mm = int(bars[i].time[14:16])
    except (ValueError, IndexError):
        return None
    if mm != 0 or hh % 4 != 0:
        return None
    if i < 1:
        return None
    try:
        ph = int(bars[i - 1].time[11:13])
        pm = int(bars[i - 1].time[14:16])
        if pm == 0 and ph % 4 == 0:
            return None
    except (ValueError, IndexError):
        pass
    if i < 50:
        return None
    bar = bars[i]
    if bar.atr <= 0 or bar.ema20 >= bar.ema50 or bar.close >= bar.ema50:
        return None
    prior_low = min(b.low for b in bars[i - 16 : i])
    if bar.close < prior_low:
        return -1
    return None


def _signal_streak_down_days_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Sparse: 3 consecutive UTC-day down closes, enter on 3rd day open bar."""
    bpd = _bars_per_day(config)
    if bpd > 1 and not _is_new_utc_day(bars, i):
        return None
    if bpd == 1:
        # native daily: last 3 closes declining
        if i < 4:
            return None
        if (
            bars[i - 1].close < bars[i - 2].close < bars[i - 3].close
            and bars[i].close < bars[i].ema50
        ):
            return -1
        return None
    day_idx: list[int] = []
    for j in range(i, max(-1, i - bpd * 10), -1):
        if j == i or _is_new_utc_day(bars, j):
            day_idx.append(j)
        if len(day_idx) >= 4:
            break
    if len(day_idx) < 4:
        return None
    c0 = bars[day_idx[1]].close
    c1 = bars[day_idx[2]].close
    c2 = bars[day_idx[3]].close
    if c0 < c1 < c2 and bars[i].close < bars[i].ema50:
        return -1
    return None


def _signal_streak_up_days_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    bpd = _bars_per_day(config)
    if bpd > 1 and not _is_new_utc_day(bars, i):
        return None
    if bpd == 1:
        if i < 4:
            return None
        if (
            bars[i - 1].close > bars[i - 2].close > bars[i - 3].close
            and bars[i].close > bars[i].ema50
        ):
            return 1
        return None
    day_idx: list[int] = []
    for j in range(i, max(-1, i - bpd * 10), -1):
        if j == i or _is_new_utc_day(bars, j):
            day_idx.append(j)
        if len(day_idx) >= 4:
            break
    if len(day_idx) < 4:
        return None
    c0 = bars[day_idx[1]].close
    c1 = bars[day_idx[2]].close
    c2 = bars[day_idx[3]].close
    if c0 > c1 > c2 and bars[i].close > bars[i].ema50:
        return 1
    return None


def _signal_weekly_mom_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Only Mondays UTC: close < close 7d ago and ema50 falling."""
    bpd = _bars_per_day(config)
    if bpd > 1 and not _is_new_utc_day(bars, i):
        return None
    try:
        from datetime import datetime, timezone

        dt = datetime.strptime(bars[i].time[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if dt.weekday() != 0:  # Monday
            return None
    except ValueError:
        return None
    n = bpd * 7
    if i < n + 5:
        return None
    bar = bars[i]
    if bar.atr <= 0:
        return None
    if bar.close < bars[i - n].close and bar.ema50 < bars[i - bpd].ema50:
        return -1
    return None


def _signal_weekly_mom_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    bpd = _bars_per_day(config)
    if bpd > 1 and not _is_new_utc_day(bars, i):
        return None
    try:
        from datetime import datetime, timezone

        dt = datetime.strptime(bars[i].time[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if dt.weekday() != 0:
            return None
    except ValueError:
        return None
    n = bpd * 7
    if i < n + 5:
        return None
    bar = bars[i]
    if bar.atr <= 0:
        return None
    if bar.close > bars[i - n].close and bar.ema50 > bars[i - bpd].ema50:
        return 1
    return None


def _atr_pct_rank(bars: list[FeatureBar], i: int, lookback: int = 96) -> float | None:
    """Percentile rank of current atr_pct in trailing window (0..1)."""
    if i < lookback or lookback < 8:
        return None
    window = [b.atr_pct for b in bars[i - lookback + 1 : i + 1] if b.atr_pct > 0]
    if len(window) < lookback // 2:
        return None
    cur = bars[i].atr_pct
    if cur <= 0:
        return None
    return sum(1 for x in window if x <= cur) / float(len(window))


def _utc_hour(bar: FeatureBar) -> int | None:
    try:
        # quantify time "YYYY-MM-DD HH:MM:SS"
        return int(bar.time[11:13])
    except (TypeError, ValueError, IndexError):
        return None


def _signal_high_vol_donchian_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Donchian long only when ATR% is elevated (regime filter)."""
    d = _signal_donchian_breakout(bars, i, config)
    if d != 1:
        return None
    bpd = _bars_per_day(config)
    rank = _atr_pct_rank(bars, i, lookback=max(48, bpd * 5))
    if rank is None or rank < 0.70:
        return None
    return 1


def _signal_high_vol_donchian_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    d = _signal_donchian_short(bars, i, config)
    if d != -1:
        return None
    bpd = _bars_per_day(config)
    rank = _atr_pct_rank(bars, i, lookback=max(48, bpd * 5))
    if rank is None or rank < 0.70:
        return None
    return -1


def _signal_low_vol_bb_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """BB mean-revert long only in compressed vol."""
    d = _signal_bb_mean_revert_long(bars, i, config)
    if d != 1:
        return None
    bpd = _bars_per_day(config)
    rank = _atr_pct_rank(bars, i, lookback=max(48, bpd * 5))
    if rank is None or rank > 0.40:
        return None
    return 1


def _signal_low_vol_bb_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    d = _signal_bb_mean_revert_short(bars, i, config)
    if d != -1:
        return None
    bpd = _bars_per_day(config)
    rank = _atr_pct_rank(bars, i, lookback=max(48, bpd * 5))
    if rank is None or rank > 0.40:
        return None
    return -1


def _signal_failed_breakout_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Prior bar closed above recent channel high; current reclaims below — short."""
    look = int(getattr(config, "donchian_lookback", 55) or 55)
    if i < look + 3:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0:
        return None
    channel = bars[i - look : i - 1]
    if not channel:
        return None
    prior_high = max(b.high for b in channel)
    # breakout attempt then failure
    if prev.close > prior_high and bar.close < prior_high and bar.close < bar.ema20:
        return -1
    return None


def _signal_failed_breakdown_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    look = int(getattr(config, "donchian_lookback", 55) or 55)
    if i < look + 3:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0:
        return None
    channel = bars[i - look : i - 1]
    if not channel:
        return None
    prior_low = min(b.low for b in channel)
    if prev.close < prior_low and bar.close > prior_low and bar.close > bar.ema20:
        return 1
    return None


def _signal_ny_session_mom_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """US cash-ish hours UTC 13–20: multi-day momentum short only in session."""
    hour = _utc_hour(bars[i])
    if hour is None or hour < 13 or hour > 20:
        return None
    return _signal_multi_day_momentum_short(bars, i, config)


def _signal_ny_session_mom_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    hour = _utc_hour(bars[i])
    if hour is None or hour < 13 or hour > 20:
        return None
    return _signal_multi_day_momentum_long(bars, i, config)


def _signal_asia_session_range_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Asia UTC 0–8: BB fade short only (range hypothesis)."""
    hour = _utc_hour(bars[i])
    if hour is None or hour > 8:
        return None
    return _signal_bb_mean_revert_short(bars, i, config)


def _signal_asia_session_range_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    hour = _utc_hour(bars[i])
    if hour is None or hour > 8:
        return None
    return _signal_bb_mean_revert_long(bars, i, config)


def _signal_outside_reversal_short(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Bearish outside bar after local upswing."""
    if i < 5:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0:
        return None
    if bar.high >= prev.high and bar.low <= prev.low and bar.close < prev.low:
        # local upswing: close 3 bars ago below current open area
        if bars[i - 3].close < bar.open and bar.close < bar.ema20:
            return -1
    return None


def _signal_outside_reversal_long(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    if i < 5:
        return None
    bar, prev = bars[i], bars[i - 1]
    if bar.atr <= 0:
        return None
    if bar.high >= prev.high and bar.low <= prev.low and bar.close > prev.high:
        if bars[i - 3].close > bar.open and bar.close > bar.ema20:
            return 1
    return None


def _signal_table() -> dict:
    return {
        "donchian_breakout": _signal_donchian_breakout,
        "donchian_short": _signal_donchian_short,
        "htf_pullback": _signal_htf_pullback,
        "htf_pullback_short": _signal_htf_pullback_short,
        "ema_cross_long": _signal_ema_cross_long,
        "ema_cross_short": _signal_ema_cross_short,
        "bb_mean_revert_long": _signal_bb_mean_revert_long,
        "bb_mean_revert_short": _signal_bb_mean_revert_short,
        "vol_donchian_long": _signal_vol_donchian_long,
        "rsi_trend_long": _signal_rsi_trend_long,
        "rsi_trend_short": _signal_rsi_trend_short,
        "daily_breakout_long": _signal_daily_breakout_long,
        "daily_breakout_short": _signal_daily_breakout_short,
        "slow_ema_cross_long": _signal_slow_ema_cross_long,
        "slow_ema_cross_short": _signal_slow_ema_cross_short,
        "atr_squeeze_breakout_long": _signal_atr_squeeze_breakout_long,
        "atr_squeeze_breakout_short": _signal_atr_squeeze_breakout_short,
        "multi_day_momentum_long": _signal_multi_day_momentum_long,
        "multi_day_momentum_short": _signal_multi_day_momentum_short,
        "four_h_close_trend_long": _signal_4h_close_trend_long,
        "four_h_close_trend_short": _signal_4h_close_trend_short,
        "streak_down_days_short": _signal_streak_down_days_short,
        "streak_up_days_long": _signal_streak_up_days_long,
        "weekly_mom_short": _signal_weekly_mom_short,
        "weekly_mom_long": _signal_weekly_mom_long,
        # v7 structural families
        "high_vol_donchian_long": _signal_high_vol_donchian_long,
        "high_vol_donchian_short": _signal_high_vol_donchian_short,
        "low_vol_bb_long": _signal_low_vol_bb_long,
        "low_vol_bb_short": _signal_low_vol_bb_short,
        "failed_breakout_short": _signal_failed_breakout_short,
        "failed_breakdown_long": _signal_failed_breakdown_long,
        "ny_session_mom_short": _signal_ny_session_mom_short,
        "ny_session_mom_long": _signal_ny_session_mom_long,
        "asia_session_range_short": _signal_asia_session_range_short,
        "asia_session_range_long": _signal_asia_session_range_long,
        "outside_reversal_short": _signal_outside_reversal_short,
        "outside_reversal_long": _signal_outside_reversal_long,
    }


# dual_* families map to a base single-name family; both symbols must agree.
DUAL_FAMILY_BASE: dict[str, str] = {
    "dual_md_mom_short": "multi_day_momentum_short",
    "dual_md_mom_long": "multi_day_momentum_long",
    "dual_daily_breakout_short": "daily_breakout_short",
    "dual_daily_breakout_long": "daily_breakout_long",
    "dual_streak_down_short": "streak_down_days_short",
    "dual_weekly_mom_short": "weekly_mom_short",
    "dual_failed_breakout_short": "failed_breakout_short",
    "dual_high_vol_donchian_short": "high_vol_donchian_short",
    "dual_ny_session_mom_short": "ny_session_mom_short",
}


def _signal_direction(
    bars: list[FeatureBar], i: int, config: MajorsSleeveConfig
) -> int | None:
    """Return +1 long, -1 short, or None (single-symbol families)."""
    family = getattr(config, "signal_family", "donchian_breakout") or "donchian_breakout"
    if family.startswith("dual_"):
        # Dual evaluated at portfolio entry scan, not per-bar alone
        return None
    table = _signal_table()
    fn = table.get(family, _signal_donchian_breakout)
    return fn(bars, i, config)


def _direction_with_family(
    bars: list[FeatureBar],
    i: int,
    config: MajorsSleeveConfig,
    family: str,
) -> int | None:
    table = _signal_table()
    fn = table.get(family)
    if fn is None:
        return None
    # Temporarily treat as non-dual family
    return fn(bars, i, config)


def _funding_allows(bar: FeatureBar, direction: int, funding_filter: str) -> bool:
    """Optional entry gate using FeatureBar.funding_rate if present."""
    if not funding_filter or funding_filter == "none":
        return True
    rate = getattr(bar, "funding_rate", None)
    if rate is None:
        return False  # filter requested but no funding feature
    if funding_filter == "short_funding_positive" and direction < 0:
        return float(rate) > 0.0
    if funding_filter == "short_funding_negative" and direction < 0:
        return float(rate) < 0.0
    if funding_filter == "long_funding_negative" and direction > 0:
        return float(rate) < 0.0
    if funding_filter == "long_funding_positive" and direction > 0:
        return float(rate) > 0.0
    return True


def resolve_entry_signal(
    market: MarketMap,
    index: dict[str, dict[int, int]],
    ts: int,
    config: MajorsSleeveConfig,
    run_symbols: tuple[str, ...],
    funding_filter: str = "none",
) -> tuple[str, int] | None:
    """Return (symbol, direction) or None. Handles dual-confirm families."""
    family = getattr(config, "signal_family", "donchian_breakout") or "donchian_breakout"
    if family.startswith("dual_"):
        base = DUAL_FAMILY_BASE.get(family)
        if not base or len(run_symbols) < 2:
            return None
        dirs: dict[str, int] = {}
        for sym in run_symbols:
            i = index.get(sym, {}).get(ts)
            if i is None:
                return None
            d = _direction_with_family(market[sym], i, config, base)
            if d is None:
                return None
            if not _funding_allows(market[sym][i], d, funding_filter):
                return None
            dirs[sym] = d
        first = dirs[run_symbols[0]]
        if any(dirs[s] != first for s in run_symbols):
            return None
        return run_symbols[0], first

    # Relative-weak short: among names with multi-day down mom, pick worst 5d return.
    if family == "rel_weak_md_mom_short":
        bpd = _bars_per_day(config)
        n = 5 * bpd
        candidates: list[tuple[str, float]] = []
        for sym in run_symbols:
            i = index.get(sym, {}).get(ts)
            if i is None or i < n + 5:
                continue
            d = _direction_with_family(
                market[sym], i, config, "multi_day_momentum_short"
            )
            if d != -1:
                continue
            if not _funding_allows(market[sym][i], -1, funding_filter):
                continue
            bars = market[sym]
            ret = bars[i].close / bars[i - n].close - 1.0
            candidates.append((sym, ret))
        if not candidates:
            return None
        # worst (most negative) relative return
        sym = min(candidates, key=lambda x: x[1])[0]
        return sym, -1

    # Relative-strong long: pick best 5d return among multi-day long signals.
    if family == "rel_strong_md_mom_long":
        bpd = _bars_per_day(config)
        n = 5 * bpd
        candidates: list[tuple[str, float]] = []
        for sym in run_symbols:
            i = index.get(sym, {}).get(ts)
            if i is None or i < n + 5:
                continue
            d = _direction_with_family(
                market[sym], i, config, "multi_day_momentum_long"
            )
            if d != 1:
                continue
            if not _funding_allows(market[sym][i], 1, funding_filter):
                continue
            bars = market[sym]
            ret = bars[i].close / bars[i - n].close - 1.0
            candidates.append((sym, ret))
        if not candidates:
            return None
        sym = max(candidates, key=lambda x: x[1])[0]
        return sym, 1

    for sym in run_symbols:
        i = index.get(sym, {}).get(ts)
        if i is None:
            continue
        d = _signal_direction(market[sym], i, config)
        if d is None:
            continue
        if not _funding_allows(market[sym][i], d, funding_filter):
            continue
        return sym, d
    return None


def _signal_long(bars: list[FeatureBar], i: int, config: MajorsSleeveConfig) -> bool:
    """Back-compat: True only for long signals."""
    return _signal_direction(bars, i, config) == 1


def load_majors_market(
    data_dir: Path,
    config: MajorsSleeveConfig | None = None,
) -> MarketMap:
    cfg = config or MajorsSleeveConfig()
    return load_market(
        data_dir,
        cfg.timeframe_minutes,
        symbols=set(cfg.symbols),
    )


def _config_with_equity(base: MajorsSleeveConfig, equity0: float) -> MajorsSleeveConfig:
    """Preserve rule fields when only start_equity changes."""
    if abs(equity0 - base.start_equity) <= 1e-12:
        return base
    payload = {**asdict_safe(base), "start_equity": equity0}
    return MajorsSleeveConfig(**payload)


def asdict_safe(cfg: MajorsSleeveConfig) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(cfg)


def replay_majors_account(
    data_dir: Path,
    *,
    config: MajorsSleeveConfig | None = None,
    start_equity: float | None = None,
    max_bars: int | None = None,
    market: MarketMap | None = None,
    symbol_subset: tuple[str, ...] | None = None,
    common_timestamps: list[int] | None = None,
    timeline_side: str = "last",
    funding_filter: str = "none",
) -> dict[str, Any]:
    """Walk BTC/ETH bars and produce an account fingerprint summary.

    Optional research controls:
    - symbol_subset: trade only these production-bound symbols
    - common_timestamps: explicit timeline (overrides max_bars slice)
    - timeline_side: when max_bars set, take 'first' or 'last' of common
    - funding_filter: none | short_funding_positive | short_funding_negative | ...
    """
    base = config or MajorsSleeveConfig()
    equity0 = float(start_equity if start_equity is not None else base.start_equity)
    equity_check = validate_start_equity(equity0)
    active_symbols = tuple(symbol_subset) if symbol_subset is not None else base.symbols
    universe = validate_production_bound_universe(active_symbols)
    sid = base.strategy_id
    if not equity_check.accepted:
        return {
            "report_type": "majors_account_replay",
            "strategy_id": sid,
            "formal_status": "rejected_equity_policy",
            "start_equity_validation": equity_check.to_dict(),
            "universe_validation": universe.to_dict(),
            "config_fingerprint": base.fingerprint(),
        }
    # Single-symbol diagnostic is allowed if each symbol is production-bound
    if any(not validate_production_bound_universe([s]).classifications[0].production_bound for s in active_symbols):
        return {
            "report_type": "majors_account_replay",
            "strategy_id": sid,
            "formal_status": "rejected_universe",
            "start_equity_validation": equity_check.to_dict(),
            "universe_validation": universe.to_dict(),
            "config_fingerprint": base.fingerprint(),
        }

    cfg = _config_with_equity(base, equity0)
    # Temporary symbol list for this run (do not mutate frozen config fingerprint)
    run_symbols = active_symbols

    if market is None:
        market = load_market(
            data_dir,
            cfg.timeframe_minutes,
            symbols=set(run_symbols),
        )
    else:
        market = {s: market[s] for s in run_symbols if s in market}
    if len(market) < 1:
        return {
            "report_type": "majors_account_replay",
            "strategy_id": cfg.strategy_id,
            "formal_status": "data_missing",
            "symbols_loaded": sorted(market.keys()),
            "config_fingerprint": cfg.fingerprint(),
        }

    # Common timeline (intersection)
    if common_timestamps is not None:
        common = list(common_timestamps)
    else:
        ts_sets = [{b.ts for b in bars} for bars in market.values()]
        common = sorted(set.intersection(*ts_sets)) if len(ts_sets) > 1 else sorted(ts_sets[0])
        if max_bars is not None and len(common) > max_bars:
            if timeline_side == "first":
                common = common[:max_bars]
            else:
                common = common[-max_bars:]

    index: dict[str, dict[int, int]] = {}
    for sym, bars in market.items():
        index[sym] = {b.ts: i for i, b in enumerate(bars)}

    equity = equity0
    peak = equity0
    open_pos: _OpenPos | None = None
    trades: list[dict[str, Any]] = []
    cost_rate = _one_way_cost_rate(cfg)
    permanent = "active"

    for ts in common:
        # Manage open
        if open_pos is not None:
            bars = market[open_pos.symbol]
            i = index[open_pos.symbol][ts]
            bar = bars[i]
            exit_price = None
            exit_reason = None
            direction = int(open_pos.direction)
            if direction >= 0:
                if bar.low <= open_pos.stop:
                    exit_price = open_pos.stop
                    exit_reason = "stop"
                elif bar.high >= open_pos.take_profit:
                    exit_price = open_pos.take_profit
                    exit_reason = "take_profit"
                else:
                    new_trail = bar.close - cfg.trailing_atr * bar.atr
                    if new_trail > open_pos.trail:
                        open_pos.trail = new_trail
                        open_pos.stop = max(open_pos.stop, new_trail)
                    held = i - open_pos.entry_idx
                    if held >= cfg.max_hold_bars:
                        exit_price = bar.close
                        exit_reason = "time_stop"
            else:
                # short: stop above, TP below
                if bar.high >= open_pos.stop:
                    exit_price = open_pos.stop
                    exit_reason = "stop"
                elif bar.low <= open_pos.take_profit:
                    exit_price = open_pos.take_profit
                    exit_reason = "take_profit"
                else:
                    new_trail = bar.close + cfg.trailing_atr * bar.atr
                    if new_trail < open_pos.trail:
                        open_pos.trail = new_trail
                        open_pos.stop = min(open_pos.stop, new_trail)
                    held = i - open_pos.entry_idx
                    if held >= cfg.max_hold_bars:
                        exit_price = bar.close
                        exit_reason = "time_stop"

            if exit_price is not None:
                if direction >= 0:
                    fill = exit_price * (1.0 - cost_rate)
                    pnl = (fill - open_pos.entry_price) * open_pos.qty
                    dir_label = "long"
                else:
                    fill = exit_price * (1.0 + cost_rate)
                    pnl = (open_pos.entry_price - fill) * open_pos.qty
                    dir_label = "short"
                equity = max(0.0, equity + pnl)
                peak = max(peak, equity)
                trades.append(
                    {
                        "symbol": open_pos.symbol,
                        "direction": dir_label,
                        "entry_price": open_pos.entry_price,
                        "exit_price": fill,
                        "net_pnl": pnl,
                        "exit_reason": exit_reason,
                        "entry_ts": bars[open_pos.entry_idx].ts,
                        "exit_ts": bar.ts,
                    }
                )
                open_pos = None
                if equity <= cfg.ruin_equity:
                    permanent = "ruined"
                    break
                dd = 1.0 - equity / peak if peak > 0 else 0.0
                if dd >= cfg.peak_drawdown_halt:
                    permanent = "peak_drawdown_halt"
                    break

        if open_pos is not None or permanent != "active":
            continue

        # Entry scan (supports dual-confirm + optional funding gate)
        resolved = resolve_entry_signal(
            market, index, ts, cfg, run_symbols, funding_filter=funding_filter
        )
        if resolved is None:
            continue
        sym, direction = resolved
        i = index[sym][ts]
        bar = market[sym][i]
        if direction > 0:
            raw_entry = bar.close * (1.0 + cost_rate)
            stop = raw_entry - cfg.stop_atr * bar.atr
            tp = raw_entry + cfg.take_profit_atr * bar.atr
        else:
            raw_entry = bar.close * (1.0 - cost_rate)
            stop = raw_entry + cfg.stop_atr * bar.atr
            tp = raw_entry - cfg.take_profit_atr * bar.atr
        sized = _size_position(equity, raw_entry, stop, cfg)
        if sized is None:
            continue
        qty, notional, margin = sized
        open_pos = _OpenPos(
            symbol=sym,
            direction=int(direction),
            entry_idx=i,
            entry_price=raw_entry,
            qty=qty,
            notional=notional,
            margin=margin,
            stop=stop,
            take_profit=tp,
            trail=stop,
            entry_equity=equity,
        )

    # Force-close at end for fingerprint completeness
    if open_pos is not None and permanent == "active":
        bars = market[open_pos.symbol]
        bar = bars[-1]
        if open_pos.direction >= 0:
            fill = bar.close * (1.0 - cost_rate)
            pnl = (fill - open_pos.entry_price) * open_pos.qty
            dir_label = "long"
        else:
            fill = bar.close * (1.0 + cost_rate)
            pnl = (open_pos.entry_price - fill) * open_pos.qty
            dir_label = "short"
        equity = max(0.0, equity + pnl)
        trades.append(
            {
                "symbol": open_pos.symbol,
                "direction": dir_label,
                "entry_price": open_pos.entry_price,
                "exit_price": fill,
                "net_pnl": pnl,
                "exit_reason": "end_of_data",
                "entry_ts": bars[open_pos.entry_idx].ts,
                "exit_ts": bar.ts,
            }
        )
        open_pos = None

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    pf = (gross_win / gross_loss) if gross_loss > 1e-12 else (1e9 if gross_win > 0 else 0.0)
    # crude max DD from trade path
    eq = equity0
    peak_eq = equity0
    max_dd = 0.0
    for t in trades:
        eq = max(0.0, eq + float(t["net_pnl"]))
        peak_eq = max(peak_eq, eq)
        if peak_eq > 0:
            max_dd = max(max_dd, 1.0 - eq / peak_eq)

    return {
        "report_type": "majors_account_replay",
        "strategy_id": cfg.strategy_id,
        "track": cfg.track,
        "formal_status": "ok",
        "config_fingerprint": cfg.fingerprint(),
        "symbols": list(run_symbols),
        "track_class": "production_bound",
        "demo_live_graduation_eligible": len(run_symbols) >= 2,
        "places_exchange_orders": False,
        "live_allowed": False,
        "start_equity_validation": equity_check.to_dict(),
        "universe_validation": universe.to_dict(),
        "account": {
            "trades": len(trades),
            "starting_equity": equity0,
            "ending_equity": equity,
            "max_drawdown_fraction": max_dd,
            "profit_factor": pf,
            "permanent_account_state": permanent,
            "trades_detail": trades,
        },
        "bars_common": len(common),
        "notes": (
            "Offline fingerprint only. Not a trading authorization. "
            "Default pipeline places no exchange orders."
        ),
    }


def write_majors_replay_report(report: dict[str, Any], path: Path) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
