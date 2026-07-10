"""L1 — Transition Candidate Pool.

Collects ALL near-action candidates (breakout, pullback, reclaim, volume surge,
EMA turn, range revert) without filtering for actual entry.
Each candidate is a snapshot of market features at that moment.

Design: relaxed thresholds (≈60-70% of real signal requirements) to cast a wide net.
The downstream MFE/MAE labeler and ML filter decide which candidates are worth trading.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from market import FeatureBar


@dataclass(slots=True)
class Candidate:
    """One near-action snapshot.  All floats rounded to 6dp for compact JSON."""
    symbol: str
    ts: int
    time: str
    direction: int          # 1 = long, -1 = short
    regime: str             # uptrend / downtrend / range / transition
    pattern_type: str       # breakout / pullback / reclaim / volume_surge / ema_turn / range_revert
    proximity_score: float  # 0-1, how close to a real signal (1 = would have fired)

    # --- price context ---
    close: float
    open_: float
    high: float
    low: float
    ema20: float
    ema50: float
    ema200: float
    atr: float
    atr_pct: float
    rsi: float
    bb_upper: float
    bb_lower: float
    bb_mid: float
    donchian_high: float
    donchian_low: float
    trend_strength: float
    vol_ratio: float        # volume / vol_sma
    candle_body_pct: float  # abs(close-open)/close
    candle_range_pct: float # (high-low)/close
    move_1d: float          # close / lookback_96 - 1

    # --- optional enriched features ---
    funding_rate: float = 0.0
    open_interest_change_pct: float = 0.0
    trade_flow_imbalance: float = 0.0
    depth_imbalance: float = 0.0

    # --- MFE/MAE labels (filled by mfe_labeler) ---
    mfe_pct: float = -1.0   # max favorable excursion % (forward)
    mae_pct: float = -1.0   # max adverse excursion % (forward)
    forward_pnl_pct: float = -999.0  # actual PnL at fixed horizon
    label: int = -1         # 1=profitable, 0=not, -1=unlabeled
    label_horizon_bars: int = 0


# ---------------------------------------------------------------------------
# Pattern detectors — relaxed versions of strategy.py signals
# ---------------------------------------------------------------------------

def _near_breakout_long(bar: FeatureBar, prev: FeatureBar, vol_ratio: float) -> float:
    """How close is this bar to a donchian-high breakout long? Returns 0-1 proximity."""
    price_prox = bar.close / bar.donchian_high if bar.donchian_high > 0 else 0.0
    if price_prox < 0.990:
        return 0.0
    vol_score = min(1.0, vol_ratio / 1.4)
    ema_ok = 1.0 if bar.ema20 >= bar.ema50 else 0.3
    price_score = min(1.0, (price_prox - 0.990) / 0.012)  # 0.990→0 score, 1.002→1
    return round(min(1.0, price_score * 0.5 + vol_score * 0.3 + ema_ok * 0.2), 4)


def _near_breakout_short(bar: FeatureBar, prev: FeatureBar, vol_ratio: float) -> float:
    price_prox = bar.donchian_low / bar.close if bar.close > 0 else 0.0
    if price_prox < 0.990:
        return 0.0
    vol_score = min(1.0, vol_ratio / 1.4)
    ema_ok = 1.0 if bar.ema20 <= bar.ema50 else 0.3
    price_score = min(1.0, (price_prox - 0.990) / 0.012)
    return round(min(1.0, price_score * 0.5 + vol_score * 0.3 + ema_ok * 0.2), 4)


def _near_pullback_long(bar: FeatureBar, prev: FeatureBar, vol_ratio: float) -> float:
    """Price just below EMA20, bouncing up — near pullback long."""
    if bar.ema20 <= 0:
        return 0.0
    dist = (bar.close - bar.ema20) / bar.ema20  # negative = below
    if dist > 0.01 or dist < -0.04:  # too far above or too far below
        return 0.0
    # prev below, current approaching from below
    prev_below = 1.0 if prev.close < prev.ema20 else 0.0
    approach = min(1.0, (dist + 0.04) / 0.05)  # -0.04→0, 0.01→1
    vol_score = min(1.0, vol_ratio / 1.0)
    ema_structure = 1.0 if bar.ema20 > bar.ema50 else 0.2
    return round(min(1.0, approach * 0.4 + prev_below * 0.2 + vol_score * 0.2 + ema_structure * 0.2), 4)


def _near_pullback_short(bar: FeatureBar, prev: FeatureBar, vol_ratio: float) -> float:
    if bar.ema20 <= 0:
        return 0.0
    dist = (bar.ema20 - bar.close) / bar.ema20  # negative = above
    if dist > 0.01 or dist < -0.04:
        return 0.0
    prev_above = 1.0 if prev.close > prev.ema20 else 0.0
    approach = min(1.0, (dist + 0.04) / 0.05)
    vol_score = min(1.0, vol_ratio / 1.0)
    ema_structure = 1.0 if bar.ema20 < bar.ema50 else 0.2
    return round(min(1.0, approach * 0.4 + prev_above * 0.2 + vol_score * 0.2 + ema_structure * 0.2), 4)


def _near_reclaim_long(bar: FeatureBar, prev: FeatureBar, vol_ratio: float) -> float:
    """Price reclaiming EMA20 from below after a dip."""
    if bar.ema20 <= 0:
        return 0.0
    crossed = prev.close < prev.ema20 and bar.close > bar.ema20
    if not crossed:
        return 0.0
    strength = min(1.0, (bar.close - bar.ema20) / (bar.atr_pct * bar.close + 1e-10) / 2.0)
    vol_score = min(1.0, vol_ratio / 1.0)
    ema_structure = 1.0 if bar.ema20 > bar.ema50 else 0.3
    return round(min(1.0, strength * 0.4 + vol_score * 0.3 + ema_structure * 0.3), 4)


def _near_reclaim_short(bar: FeatureBar, prev: FeatureBar, vol_ratio: float) -> float:
    if bar.ema20 <= 0:
        return 0.0
    crossed = prev.close > prev.ema20 and bar.close < bar.ema20
    if not crossed:
        return 0.0
    strength = min(1.0, (bar.ema20 - bar.close) / (bar.atr_pct * bar.close + 1e-10) / 2.0)
    vol_score = min(1.0, vol_ratio / 1.0)
    ema_structure = 1.0 if bar.ema20 < bar.ema50 else 0.3
    return round(min(1.0, strength * 0.4 + vol_score * 0.3 + ema_structure * 0.3), 4)


def _near_volume_surge_long(bar: FeatureBar, vol_ratio: float) -> float:
    """High volume bar near resistance with bullish close."""
    if vol_ratio < 1.1:
        return 0.0
    vol_score = min(1.0, (vol_ratio - 1.1) / 0.9)  # 1.1→0, 2.0→1
    price_prox = bar.close / bar.donchian_high if bar.donchian_high > 0 else 0.0
    if price_prox < 0.985:
        return 0.0
    price_score = min(1.0, (price_prox - 0.985) / 0.017)
    bullish = 1.0 if bar.close > bar.open else 0.2
    return round(min(1.0, vol_score * 0.4 + price_score * 0.35 + bullish * 0.25), 4)


def _near_volume_surge_short(bar: FeatureBar, vol_ratio: float) -> float:
    if vol_ratio < 1.1:
        return 0.0
    vol_score = min(1.0, (vol_ratio - 1.1) / 0.9)
    price_prox = bar.donchian_low / bar.close if bar.close > 0 else 0.0
    if price_prox < 0.985:
        return 0.0
    price_score = min(1.0, (price_prox - 0.985) / 0.017)
    bearish = 1.0 if bar.close < bar.open else 0.2
    return round(min(1.0, vol_score * 0.4 + price_score * 0.35 + bearish * 0.25), 4)


def _near_ema_turn_long(bar: FeatureBar, prev: FeatureBar, prev2: FeatureBar | None) -> float:
    """EMA20 slope turning from negative to positive."""
    if prev.ema20 <= 0 or bar.ema20 <= 0:
        return 0.0
    cur_slope = bar.ema20 - prev.ema20
    if cur_slope <= 0:
        return 0.0
    if prev2 is not None and prev2.ema20 > 0:
        prev_slope = prev.ema20 - prev2.ema20
        if prev_slope > 0:
            return 0.0  # already turning, not "near"
    slope_score = min(1.0, cur_slope / (bar.atr_pct * bar.close * 0.1 + 1e-10))
    ema_structure = 1.0 if bar.ema50 > bar.ema200 else 0.3
    return round(min(1.0, slope_score * 0.6 + ema_structure * 0.4), 4)


def _near_ema_turn_short(bar: FeatureBar, prev: FeatureBar, prev2: FeatureBar | None) -> float:
    if prev.ema20 <= 0 or bar.ema20 <= 0:
        return 0.0
    cur_slope = bar.ema20 - prev.ema20
    if cur_slope >= 0:
        return 0.0
    if prev2 is not None and prev2.ema20 > 0:
        prev_slope = prev.ema20 - prev2.ema20
        if prev_slope < 0:
            return 0.0
    slope_score = min(1.0, abs(cur_slope) / (bar.atr_pct * bar.close * 0.1 + 1e-10))
    ema_structure = 1.0 if bar.ema50 < bar.ema200 else 0.3
    return round(min(1.0, slope_score * 0.6 + ema_structure * 0.4), 4)


def _near_range_revert_long(bar: FeatureBar, vol_ratio: float) -> float:
    """Price near BB lower with RSI low — range revert long."""
    if bar.bb_lower <= 0 or bar.close <= 0:
        return 0.0
    dist = (bar.close - bar.bb_lower) / bar.close
    if dist > 0.008 or dist < -0.02:
        return 0.0
    rsi_score = max(0.0, min(1.0, (45 - bar.rsi) / 20.0))  # 25→1, 45→0
    price_score = min(1.0, (0.008 - dist) / 0.028)
    vol_low = 1.0 if vol_ratio < 1.3 else 0.3
    return round(min(1.0, price_score * 0.4 + rsi_score * 0.35 + vol_low * 0.25), 4)


def _near_range_revert_short(bar: FeatureBar, vol_ratio: float) -> float:
    if bar.bb_upper <= 0 or bar.close <= 0:
        return 0.0
    dist = (bar.bb_upper - bar.close) / bar.close
    if dist > 0.008 or dist < -0.02:
        return 0.0
    rsi_score = max(0.0, min(1.0, (bar.rsi - 55) / 20.0))  # 75→1, 55→0
    price_score = min(1.0, (0.008 - dist) / 0.028)
    vol_low = 1.0 if vol_ratio < 1.3 else 0.3
    return round(min(1.0, price_score * 0.4 + rsi_score * 0.35 + vol_low * 0.25), 4)


# ---------------------------------------------------------------------------
# Main scanning function
# ---------------------------------------------------------------------------

# Minimum proximity to include a candidate
MIN_PROXIMITY = 0.15

# Pattern detectors: (name, long_fn, short_fn, default_regimes, sig_type)
# sig_type: "bpv" = (bar, prev, vol_ratio), "bv" = (bar, vol_ratio), "bpp" = (bar, prev, prev2)
_PATTERN_DETECTORS = [
    ("breakout",     _near_breakout_long,     _near_breakout_short,     ("uptrend", "transition", "downtrend"), "bpv"),
    ("pullback",     _near_pullback_long,     _near_pullback_short,     ("uptrend", "downtrend", "transition"), "bpv"),
    ("reclaim",      _near_reclaim_long,      _near_reclaim_short,      ("uptrend", "downtrend", "transition"), "bpv"),
    ("volume_surge", _near_volume_surge_long, _near_volume_surge_short, ("uptrend", "downtrend", "transition"), "bv"),
    ("ema_turn",     _near_ema_turn_long,     _near_ema_turn_short,     ("uptrend", "downtrend", "transition"), "bpp"),
    ("range_revert", _near_range_revert_long, _near_range_revert_short, ("range",), "bv"),
]


def scan_candidates(
    symbol: str,
    bars: list[FeatureBar],
    idx: int,
    min_proximity: float = MIN_PROXIMITY,
) -> list[Candidate]:
    """Scan one bar for all near-action patterns. Returns 0-N candidates."""
    if idx < 1:
        return []

    bar = bars[idx]
    prev = bars[idx - 1]
    prev2 = bars[idx - 2] if idx >= 2 else None
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
    lookback_1d = bars[max(0, idx - 96)]
    move_1d = bar.close / lookback_1d.close - 1.0 if lookback_1d.close else 0.0

    from strategy import classify_regime
    regime = classify_regime(bar)

    # Determine approximate regime for pattern matching
    regime_map = {
        "uptrend": ("uptrend",),
        "downtrend": ("downtrend",),
        "range": ("range",),
        "transition": ("transition", "uptrend", "downtrend"),
    }
    active_regimes = regime_map.get(regime, (regime,))

    candle_body_pct = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
    candle_range_pct = (bar.high - bar.low) / bar.close if bar.close else 0.0

    candidates: list[Candidate] = []

    for pattern_name, long_fn, short_fn, pattern_regimes, sig_type in _PATTERN_DETECTORS:
        # Check if this pattern is relevant for the current regime
        if not any(r in active_regimes for r in pattern_regimes):
            continue

        # Call with correct signature
        def _call(fn, sig_type):
            if sig_type == "bpv":
                return fn(bar, prev, vol_ratio)
            elif sig_type == "bv":
                return fn(bar, vol_ratio)
            elif sig_type == "bpp":
                return fn(bar, prev, prev2)
            return fn(bar, prev, vol_ratio)

        # Long
        prox_long = _call(long_fn, sig_type)
        if prox_long >= min_proximity:
            candidates.append(Candidate(
                symbol=symbol,
                ts=bar.ts,
                time=bar.time,
                direction=1,
                regime=regime,
                pattern_type=pattern_name,
                proximity_score=round(prox_long, 4),
                close=round(bar.close, 8),
                open_=round(bar.open, 8),
                high=round(bar.high, 8),
                low=round(bar.low, 8),
                ema20=round(bar.ema20, 8),
                ema50=round(bar.ema50, 8),
                ema200=round(bar.ema200, 8),
                atr=round(bar.atr, 8),
                atr_pct=round(bar.atr_pct, 6),
                rsi=round(bar.rsi, 2),
                bb_upper=round(bar.bb_upper, 8),
                bb_lower=round(bar.bb_lower, 8),
                bb_mid=round(bar.bb_mid, 8),
                donchian_high=round(bar.donchian_high, 8),
                donchian_low=round(bar.donchian_low, 8),
                trend_strength=round(bar.trend_strength, 4),
                vol_ratio=round(vol_ratio, 4),
                candle_body_pct=round(candle_body_pct, 6),
                candle_range_pct=round(candle_range_pct, 6),
                move_1d=round(move_1d, 6),
                funding_rate=round(float(getattr(bar, "funding_rate", 0.0) or 0.0), 6),
                open_interest_change_pct=round(float(getattr(bar, "open_interest_change_pct", 0.0) or 0.0), 6),
                trade_flow_imbalance=round(float(getattr(bar, "trade_flow_imbalance", 0.0) or 0.0), 6),
                depth_imbalance=round(float(getattr(bar, "depth_imbalance", 0.0) or 0.0), 6),
            ))

        # Short
        prox_short = _call(short_fn, sig_type)
        if prox_short >= min_proximity:
            candidates.append(Candidate(
                symbol=symbol,
                ts=bar.ts,
                time=bar.time,
                direction=-1,
                regime=regime,
                pattern_type=pattern_name,
                proximity_score=round(prox_short, 4),
                close=round(bar.close, 8),
                open_=round(bar.open, 8),
                high=round(bar.high, 8),
                low=round(bar.low, 8),
                ema20=round(bar.ema20, 8),
                ema50=round(bar.ema50, 8),
                ema200=round(bar.ema200, 8),
                atr=round(bar.atr, 8),
                atr_pct=round(bar.atr_pct, 6),
                rsi=round(bar.rsi, 2),
                bb_upper=round(bar.bb_upper, 8),
                bb_lower=round(bar.bb_lower, 8),
                bb_mid=round(bar.bb_mid, 8),
                donchian_high=round(bar.donchian_high, 8),
                donchian_low=round(bar.donchian_low, 8),
                trend_strength=round(bar.trend_strength, 4),
                vol_ratio=round(vol_ratio, 4),
                candle_body_pct=round(candle_body_pct, 6),
                candle_range_pct=round(candle_range_pct, 6),
                move_1d=round(move_1d, 6),
                funding_rate=round(float(getattr(bar, "funding_rate", 0.0) or 0.0), 6),
                open_interest_change_pct=round(float(getattr(bar, "open_interest_change_pct", 0.0) or 0.0), 6),
                trade_flow_imbalance=round(float(getattr(bar, "trade_flow_imbalance", 0.0) or 0.0), 6),
                depth_imbalance=round(float(getattr(bar, "depth_imbalance", 0.0) or 0.0), 6),
            ))

    return candidates


def scan_all_symbols(
    market: dict[str, list[FeatureBar]],
    timeline: list[int],
    index: dict[str, dict[int, int]],
    min_proximity: float = MIN_PROXIMITY,
) -> list[Candidate]:
    """Scan the entire market timeline for candidates. Returns all matches."""
    all_candidates: list[Candidate] = []
    for step, ts in enumerate(timeline):
        for symbol, bars in market.items():
            idx = index.get(symbol, {}).get(ts)
            if idx is None or idx < 2:
                continue
            cands = scan_candidates(symbol, bars, idx, min_proximity)
            all_candidates.extend(cands)
    return all_candidates


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_candidates(candidates: list[Candidate], path: Path) -> None:
    """Save candidates to JSON (one object per line = JSON Lines for large datasets)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for c in candidates:
            fh.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


def load_candidates(path: Path) -> list[Candidate]:
    """Load candidates from JSON Lines file."""
    candidates: list[Candidate] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            # Handle the open_ field name (open is a Python builtin)
            d["open_"] = d.get("open_", d.get("open", 0.0))
            candidates.append(Candidate(**{k: v for k, v in d.items() if k != "open"}))
    return candidates
