"""Frozen production-bound majors sleeve contract (BTC + ETH only).

Stage-1 production path: local paper / offline account fingerprint only.
Does not open OKX demo or live. Not an alpha claim — infrastructure +
rule fingerprint for graduation eligibility toward later demo stages.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from prod.policy import (
    DEFAULT_START_EQUITY_USDT,
    MAX_START_EQUITY_USDT,
    PRODUCTION_BOUND_SYMBOLS,
)


STRATEGY_ID = "prod_majors_donchian_atr_long_v1"
CONSERVATIVE_STRATEGY_ID = "prod_majors_donchian_atr_long_conservative_v1"
HTF_PULLBACK_STRATEGY_ID = "prod_majors_htf_pullback_v1"
TRACK = "production_bound_majors"
TRACK_CONSERVATIVE = "production_bound_majors_conservative"
TRACK_RESEARCH = "production_bound_majors_research"
TIMEFRAME_MINUTES = 15


@dataclass(frozen=True)
class MajorsSleeveConfig:
    """Frozen rule + capital for BTC/ETH local paper / account fingerprint."""

    strategy_id: str = STRATEGY_ID
    track: str = TRACK
    symbols: tuple[str, ...] = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
    start_equity: float = DEFAULT_START_EQUITY_USDT
    max_start_equity: float = MAX_START_EQUITY_USDT
    timeframe_minutes: int = TIMEFRAME_MINUTES
    # Costs (round-trip components, one-way rates)
    taker_fee: float = 0.0005
    slippage: float = 0.0002
    # Risk / sizing
    risk_per_trade: float = 0.10
    max_margin_fraction: float = 0.50
    max_positions: int = 1
    min_notional: float = 5.0
    max_leverage: float = 5.0
    # Signal family: donchian_breakout | htf_pullback
    signal_family: str = "donchian_breakout"
    # Signal (long-only donchian + EMA filter)
    donchian_lookback: int = 55
    ema_fast: int = 20
    ema_slow: int = 50
    min_ema_gap_fraction: float = 0.0  # require ema20 >= ema50 * (1+gap)
    pullback_lookback: int = 4  # bars for pullback touch (htf_pullback)
    htf_slope_bars: int = 16  # ~4h on 15m: ema50 slope filter
    stop_atr: float = 2.5
    take_profit_atr: float = 1.8
    trailing_atr: float = 2.0
    max_hold_bars: int = 32  # 8 hours on 15m
    # Account halt
    ruin_equity: float = 2.0
    peak_drawdown_halt: float = 0.70

    def __post_init__(self) -> None:
        if set(self.symbols) != set(PRODUCTION_BOUND_SYMBOLS):
            raise ValueError(
                "majors sleeve freezes exactly production-bound BTC+ETH symbols"
            )
        if self.start_equity < DEFAULT_START_EQUITY_USDT - 1e-12:
            raise ValueError("start_equity below default 10 USDT")
        if self.start_equity > MAX_START_EQUITY_USDT + 1e-12:
            raise ValueError("start_equity above max 500 USDT")

    def fingerprint(self) -> str:
        payload = asdict(self)
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["config_fingerprint"] = self.fingerprint()
        d["demo_live_default"] = False
        d["places_exchange_orders_default"] = False
        d["production_bound"] = True
        return d


def primary_majors_config(start_equity: float = DEFAULT_START_EQUITY_USDT) -> MajorsSleeveConfig:
    return MajorsSleeveConfig(start_equity=start_equity)


def conservative_majors_config(
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> MajorsSleeveConfig:
    """Stricter side-by-side fingerprint — not the paper runtime default.

    Lower risk, longer channel, wider stop, requires clearer EMA separation.
    Used only for offline comparison inside readiness packages.
    """
    return MajorsSleeveConfig(
        strategy_id=CONSERVATIVE_STRATEGY_ID,
        track=TRACK_CONSERVATIVE,
        start_equity=start_equity,
        signal_family="donchian_breakout",
        risk_per_trade=0.05,
        max_margin_fraction=0.35,
        max_leverage=3.0,
        donchian_lookback=80,
        min_ema_gap_fraction=0.002,
        stop_atr=3.0,
        take_profit_atr=1.5,
        trailing_atr=2.5,
        max_hold_bars=48,
        ruin_equity=2.0,
        peak_drawdown_halt=0.60,
    )


def h1_md_mom_short_config(
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> MajorsSleeveConfig:
    """Research sleeve (revoked 2026-07-17): 1h multi-day momentum short."""
    return MajorsSleeveConfig(
        strategy_id="prod_majors_h1_md_mom_short_v1",
        track=TRACK_RESEARCH,
        start_equity=start_equity,
        timeframe_minutes=60,
        signal_family="multi_day_momentum_short",
        risk_per_trade=0.08,
        max_margin_fraction=0.40,
        max_leverage=3.0,
        stop_atr=2.5,
        take_profit_atr=3.0,
        trailing_atr=2.0,
        max_hold_bars=72,
        ruin_equity=2.0,
        peak_drawdown_halt=0.70,
        donchian_lookback=24,
        htf_slope_bars=24,
        pullback_lookback=4,
    )


def h1_high_vol_donchian_short_config(
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> MajorsSleeveConfig:
    """Local paper sleeve: 1h high-vol regime donchian short (v7 gates)."""
    return MajorsSleeveConfig(
        strategy_id="prod_majors_h1_high_vol_donchian_short_v1",
        track=TRACK_RESEARCH,
        start_equity=start_equity,
        timeframe_minutes=60,
        signal_family="high_vol_donchian_short",
        risk_per_trade=0.08,
        max_margin_fraction=0.40,
        max_leverage=3.0,
        stop_atr=2.5,
        take_profit_atr=3.0,
        trailing_atr=2.0,
        max_hold_bars=48,
        ruin_equity=2.0,
        peak_drawdown_halt=0.70,
        donchian_lookback=24,
        htf_slope_bars=24,
        pullback_lookback=4,
    )


def resolve_sleeve_config(strategy_id: str) -> MajorsSleeveConfig | None:
    """Map known strategy IDs to frozen configs (paper/research)."""
    table = {
        STRATEGY_ID: primary_majors_config,
        CONSERVATIVE_STRATEGY_ID: conservative_majors_config,
        HTF_PULLBACK_STRATEGY_ID: htf_pullback_majors_config,
        "prod_majors_h1_md_mom_short_v1": h1_md_mom_short_config,
        "prod_majors_h1_high_vol_donchian_short_v1": h1_high_vol_donchian_short_config,
        "prod_majors_h1_dual_md_mom_short_v1": lambda: MajorsSleeveConfig(
            strategy_id="prod_majors_h1_dual_md_mom_short_v1",
            track=TRACK_RESEARCH,
            start_equity=DEFAULT_START_EQUITY_USDT,
            timeframe_minutes=60,
            signal_family="dual_md_mom_short",
            risk_per_trade=0.08,
            max_margin_fraction=0.40,
            max_leverage=3.0,
            stop_atr=2.5,
            take_profit_atr=3.0,
            trailing_atr=2.0,
            max_hold_bars=72,
            ruin_equity=2.0,
            peak_drawdown_halt=0.70,
            donchian_lookback=24,
            htf_slope_bars=24,
            pullback_lookback=4,
        ),
    }
    fn = table.get(strategy_id)
    return fn() if fn else None


def htf_pullback_majors_config(
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> MajorsSleeveConfig:
    """Research candidate: HTF slope + 15m EMA pullback reclaim (BTC/ETH only).

    Single frozen default rule — no parameter search.
    Not default paper runtime until separately admitted.
    """
    return MajorsSleeveConfig(
        strategy_id=HTF_PULLBACK_STRATEGY_ID,
        track=TRACK_RESEARCH,
        start_equity=start_equity,
        signal_family="htf_pullback",
        risk_per_trade=0.08,
        max_margin_fraction=0.45,
        max_leverage=4.0,
        donchian_lookback=55,  # unused by htf_pullback; kept for schema stability
        min_ema_gap_fraction=0.0,
        pullback_lookback=4,
        htf_slope_bars=16,
        stop_atr=2.2,
        take_profit_atr=2.5,
        trailing_atr=2.0,
        max_hold_bars=64,
        ruin_equity=2.0,
        peak_drawdown_halt=0.65,
    )
