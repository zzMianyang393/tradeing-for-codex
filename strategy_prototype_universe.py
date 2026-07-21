"""Strategy prototype universe: machine-readable catalog of ~30+ research-ready prototypes.

Each prototype is a hypothesis skeleton, NOT an approved strategy.
The preflight review tool uses these to filter eligible directions before coding.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class StrategyPrototype:
    strategy_id: str
    name_cn: str
    family: str
    expected_hold_days: float
    expected_events_per_month: float
    executed_legs: int
    required_data: list[str]
    uses_external_data: bool = False
    uses_hft_or_orderbook: bool = False
    uses_grid_or_martingale: bool = False
    resembles_rejected: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Prototype catalog ────────────────────────────────────────────────────────

PROTOTYPES: list[StrategyPrototype] = [

    # ═══════════════════════════════════════════════════════════════════════
    # TREND FOLLOWING
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="daily_donchian55_trend",
        name_cn="日线唐奇安55突破趋势",
        family="trend_following",
        expected_hold_days=14,
        expected_events_per_month=3,
        executed_legs=2,
        required_data=["ohlcv_daily"],
        notes="Donchian 55 breakout on daily, ATR stop, hold 7-30d. Low turnover.",
        resembles_rejected=["donchian_atr_trend_baseline"],
    ),
    StrategyPrototype(
        strategy_id="weekly_momentum_90d",
        name_cn="周线90日动量",
        family="trend_following",
        expected_hold_days=21,
        expected_events_per_month=2,
        executed_legs=2,
        required_data=["ohlcv_daily"],
        notes="90-day momentum ranking, rebalance weekly, long top-3.",
        resembles_rejected=["relative_strength_persistence"],
    ),
    StrategyPrototype(
        strategy_id="4h_ema_crossover",
        name_cn="4小时EMA交叉趋势",
        family="trend_following",
        expected_hold_days=5,
        expected_events_per_month=6,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="EMA20/50 crossover on 4h resampled bars.",
        resembles_rejected=["multi_timeframe"],
    ),
    StrategyPrototype(
        strategy_id="daily_ma_alignment",
        name_cn="日线均线多头排列趋势",
        family="trend_following",
        expected_hold_days=10,
        expected_events_per_month=3,
        executed_legs=2,
        required_data=["ohlcv_daily"],
        notes="Enter when EMA20>50>200 on daily, exit on cross-under.",
    ),
    StrategyPrototype(
        strategy_id="low_turnover_breakout_daily",
        name_cn="低换手日线突破",
        family="trend_following",
        expected_hold_days=14,
        expected_events_per_month=2,
        executed_legs=2,
        required_data=["ohlcv_daily"],
        notes="20-day high breakout on daily with 7-day min hold.",
        resembles_rejected=["donchian_atr_trend_baseline"],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # MEAN REVERSION
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="range_bb_reversal",
        name_cn="震荡行情布林带反弹",
        family="mean_reversion",
        expected_hold_days=0.5,
        expected_events_per_month=8,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="BB lower bounce in 震荡 regime. Hold max 12h.",
        resembles_rejected=["range_regime_mean_reversion_family"],
    ),
    StrategyPrototype(
        strategy_id="rsi_oversold_bounce",
        name_cn="RSI超卖反弹",
        family="mean_reversion",
        expected_hold_days=1,
        expected_events_per_month=10,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="RSI<30 bounce in range regime.",
        resembles_rejected=["range_regime_mean_reversion_family"],
    ),
    StrategyPrototype(
        strategy_id="daily_bb_mean_revert",
        name_cn="日线布林带均值回复",
        family="mean_reversion",
        expected_hold_days=5,
        expected_events_per_month=4,
        executed_legs=2,
        required_data=["ohlcv_daily"],
        notes="Daily BB lower bounce, target MA20.",
    ),
    StrategyPrototype(
        strategy_id="bias_reversion",
        name_cn="BIAS负偏离反弹",
        family="mean_reversion",
        expected_hold_days=2,
        expected_events_per_month=6,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="Price deviation from MA exceeds threshold, revert.",
        resembles_rejected=["range_regime_mean_reversion_family"],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # BREAKOUT
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="utc_session_breakout",
        name_cn="UTC时段区间突破",
        family="breakout",
        expected_hold_days=0.8,
        expected_events_per_month=20,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="00:00-04:00 range breakout. High turnover.",
        resembles_rejected=["utc_session_breakout_family"],
    ),
    StrategyPrototype(
        strategy_id="volatility_compression_breakout",
        name_cn="波动率压缩突破",
        family="breakout",
        expected_hold_days=3,
        expected_events_per_month=5,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="ATR percentile compression + Donchian breakout.",
        resembles_rejected=["vol_compression_breakout"],
    ),
    StrategyPrototype(
        strategy_id="opening_range_breakout",
        name_cn="开盘区间突破",
        family="breakout",
        expected_hold_days=0.5,
        expected_events_per_month=20,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="First 2h range breakout. Very high turnover.",
        resembles_rejected=["utc_session_breakout_family"],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # FUNDING / CARRY
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="funding_rate_carry",
        name_cn="正funding市场中性持有",
        family="funding_carry",
        expected_hold_days=1,
        expected_events_per_month=8,
        executed_legs=4,
        required_data=["funding", "ohlcv_15m"],
        notes="Long spot + short perp when funding > cost/3.",
        resembles_rejected=["positive_funding_carry"],
    ),
    StrategyPrototype(
        strategy_id="funding_extreme_reversal",
        name_cn="funding极端反转",
        family="funding_carry",
        expected_hold_days=0.5,
        expected_events_per_month=6,
        executed_legs=2,
        required_data=["funding", "ohlcv_15m"],
        notes="Fade extreme funding in range regime.",
        resembles_rejected=["range_regime_funding_extreme", "multi_coin_funding_crowding"],
    ),
    StrategyPrototype(
        strategy_id="funding_oi_trend_confirm",
        name_cn="funding+OI趋势确认",
        family="funding_carry",
        expected_hold_days=1,
        expected_events_per_month=8,
        executed_legs=2,
        required_data=["funding", "open_interest_daily", "ohlcv_15m"],
        notes="Both_up signal for trend continuation.",
        resembles_rejected=["funding_oi_time_corrected"],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # OI / LEVERAGE STATE
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="oi_divergence_signal",
        name_cn="OI背离信号",
        family="oi_leverage",
        expected_hold_days=2,
        expected_events_per_month=5,
        executed_legs=2,
        required_data=["open_interest_daily", "ohlcv_15m"],
        notes="OI rising while price falling = potential squeeze.",
    ),
    StrategyPrototype(
        strategy_id="oi_extreme_crowding",
        name_cn="OI极端拥挤",
        family="oi_leverage",
        expected_hold_days=1,
        expected_events_per_month=3,
        executed_legs=2,
        required_data=["open_interest_daily"],
        notes="OI at 95th percentile = potential reversal.",
    ),
    StrategyPrototype(
        strategy_id="leverage_ratio_reversal",
        name_cn="杠杆率反转",
        family="oi_leverage",
        expected_hold_days=2,
        expected_events_per_month=4,
        executed_legs=2,
        required_data=["open_interest_daily", "funding"],
        notes="High leverage + extreme funding = reversal candidate.",
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # CROSS-ASSET / ARBITRAGE
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="btc_alt_lead_lag",
        name_cn="BTC→山寨币领先滞后",
        family="cross_asset",
        expected_hold_days=0.25,
        expected_events_per_month=30,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="After BTC shock, alts catch up next hour.",
        resembles_rejected=["btc_alt_lead_lag"],
    ),
    StrategyPrototype(
        strategy_id="pairs_stat_arb",
        name_cn="配对统计套利",
        family="cross_asset",
        expected_hold_days=3,
        expected_events_per_month=8,
        executed_legs=4,
        required_data=["ohlcv_15m"],
        notes="Cointegrated pair mean reversion.",
        resembles_rejected=["pairs_walk_forward"],
    ),
    StrategyPrototype(
        strategy_id="basis_spread_trade",
        name_cn="期现基差套利",
        family="cross_asset",
        expected_hold_days=0.5,
        expected_events_per_month=10,
        executed_legs=4,
        required_data=["ohlcv_1m_spot", "ohlcv_1m_perp"],
        notes="Spot-perp basis trade.",
        resembles_rejected=["spot_perp_basis"],
    ),
    StrategyPrototype(
        strategy_id="calendar_spread_mr",
        name_cn="交割合约跨期价差均值回复",
        family="cross_asset",
        expected_hold_days=5,
        expected_events_per_month=4,
        executed_legs=4,
        required_data=["ohlcv_daily_futures"],
        notes="Calendar spread mean reversion.",
        resembles_rejected=["okx_futures_calendar_spread"],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # GRID / MARTINGALE (RISK BLOCKED)
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="grid_trading",
        name_cn="网格交易",
        family="grid_martingale",
        expected_hold_days=0.1,
        expected_events_per_month=200,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        uses_grid_or_martingale=True,
        notes="Fixed-interval buy/sell grid. Infinite loss risk.",
    ),
    StrategyPrototype(
        strategy_id="martingale_loss_add",
        name_cn="马丁格尔亏损加仓",
        family="grid_martingale",
        expected_hold_days=0.5,
        expected_events_per_month=50,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        uses_grid_or_martingale=True,
        notes="Double position after loss. Infinite loss risk.",
    ),
    StrategyPrototype(
        strategy_id="locking_hedge",
        name_cn="锁仓对冲",
        family="grid_martingale",
        expected_hold_days=1,
        expected_events_per_month=20,
        executed_legs=4,
        required_data=["ohlcv_15m"],
        uses_grid_or_martingale=True,
        notes="Lock losing position with opposite trade. Cost accumulation.",
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # EVENT / NEWS / MACRO (DATA BLOCKED)
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="news_sentiment_trade",
        name_cn="新闻舆情交易",
        family="event_news",
        expected_hold_days=0.5,
        expected_events_per_month=10,
        executed_legs=2,
        required_data=["news_api", "ohlcv_15m"],
        uses_external_data=True,
        notes="Trade on news sentiment. No free reproducible data.",
    ),
    StrategyPrototype(
        strategy_id="macro_event_trade",
        name_cn="宏观事件交易",
        family="event_news",
        expected_hold_days=1,
        expected_events_per_month=4,
        executed_legs=2,
        required_data=["macro_calendar", "ohlcv_15m"],
        uses_external_data=True,
        notes="Trade around CPI/FOMC. Non-OKX data.",
    ),
    StrategyPrototype(
        strategy_id="social_media_signal",
        name_cn="社交媒体信号",
        family="event_news",
        expected_hold_days=0.5,
        expected_events_per_month=15,
        executed_legs=2,
        required_data=["social_api", "ohlcv_15m"],
        uses_external_data=True,
        notes="Twitter/Reddit sentiment. No free reproducible history.",
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # MACHINE LEARNING (FROZEN)
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="ml_price_prediction",
        name_cn="ML价格预测",
        family="machine_learning",
        expected_hold_days=1,
        expected_events_per_month=20,
        executed_legs=2,
        required_data=["ohlcv_15m", "funding", "open_interest_daily"],
        notes="Supervised ML on price features. Overfitting risk.",
    ),
    StrategyPrototype(
        strategy_id="ml_regime_classifier",
        name_cn="ML行情分类器",
        family="machine_learning",
        expected_hold_days=3,
        expected_events_per_month=8,
        executed_legs=2,
        required_data=["ohlcv_15m"],
        notes="Classify regime with ML, trade accordingly.",
    ),
    StrategyPrototype(
        strategy_id="rl_dynamic_router",
        name_cn="强化学习动态路由",
        family="machine_learning",
        expected_hold_days=1,
        expected_events_per_month=30,
        executed_legs=2,
        required_data=["ohlcv_15m", "funding"],
        notes="RL agent selects strategy per state.",
        resembles_rejected=["ml_dynamic_router_family"],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # HFT / ORDERBOOK (DATA BLOCKED)
    # ═══════════════════════════════════════════════════════════════════════

    StrategyPrototype(
        strategy_id="orderbook_imbalance",
        name_cn="盘口不平衡信号",
        family="hft_microstructure",
        expected_hold_days=0.01,
        expected_events_per_month=500,
        executed_legs=2,
        required_data=["order_book"],
        uses_hft_or_orderbook=True,
        notes="Order book imbalance signal. No free history.",
    ),
    StrategyPrototype(
        strategy_id="tick_momentum",
        name_cn="逐笔动量",
        family="hft_microstructure",
        expected_hold_days=0.005,
        expected_events_per_month=1000,
        executed_legs=2,
        required_data=["tick_data"],
        uses_hft_or_orderbook=True,
        notes="Tick-level momentum. No free tick history.",
    ),
    StrategyPrototype(
        strategy_id="liquidation_cascade",
        name_cn="清算级联交易",
        family="hft_microstructure",
        expected_hold_days=0.1,
        expected_events_per_month=20,
        executed_legs=2,
        required_data=["liquidation_data"],
        uses_hft_or_orderbook=True,
        notes="Trade on liquidation cascades. Data coverage 0%.",
    ),
]


def get_prototypes() -> list[StrategyPrototype]:
    """Return all prototypes."""
    return list(PROTOTYPES)


def get_prototype_by_id(strategy_id: str) -> StrategyPrototype | None:
    """Look up a prototype by ID."""
    for p in PROTOTYPES:
        if p.strategy_id == strategy_id:
            return p
    return None


def get_prototypes_by_family(family: str) -> list[StrategyPrototype]:
    """Return all prototypes in a family."""
    return [p for p in PROTOTYPES if p.family == family]


if __name__ == "__main__":
    print(f"Total prototypes: {len(PROTOTYPES)}")
    families = set(p.family for p in PROTOTYPES)
    for fam in sorted(families):
        count = len(get_prototypes_by_family(fam))
        print(f"  {fam}: {count}")
