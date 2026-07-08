"""
自适应配置: 基于行情自动选择策略

核心原则 (不过拟合):
1. 行情识别 → 策略选择 (基于市场结构, 不是历史表现)
2. 趋势市 → 只做顺势 (避免逆势亏损)
3. 震荡市 → 只做反转 (range_revert)
4. 复利滚仓 → 盈利自动加仓
"""

from config import BacktestConfig, SymbolRisk


ADAPTIVE_CONFIG = BacktestConfig(
    # === 起始资金 ===
    start_equity=10.0,
    
    # === 时间框架 ===
    timeframe_minutes=15,
    
    # === 费用 ===
    taker_fee=0.00005,
    slippage=0.0003,
    
    # === 核心风控 ===
    risk_per_trade=0.20,              # 每笔20% (复利基础)
    max_margin_fraction=0.80,
    max_total_margin_fraction=0.70,
    max_positions=5,
    active_symbol_limit=8,
    
    # === 防御模式 (权益跌破50%启动) ===
    defensive_equity_fraction=0.50,
    defensive_risk_multiplier=0.40,
    defensive_margin_fraction=0.25,
    
    # === 盈利保护 (权益超过起始150%启动) ===
    profit_lock_equity_fraction=1.50,
    profit_lock_risk_multiplier=0.60,
    profit_lock_margin_fraction=0.50,
    
    # === 波动率目标 ===
    volatility_target_atr_pct=0.025,
    volatility_risk_floor=0.50,
    volatility_risk_power=0.80,
    
    # === 单笔最大亏损 ===
    max_trade_loss_pct_equity=8.0,
    
    # === 趋势策略参数 ===
    stop_atr=2.5,                     # 趋势宽止损 (给趋势呼吸空间)
    take_profit_atr=4.0,              # 趋势宽止盈 (让利润奔跑)
    trailing_atr=1.8,                 # 追踪止损 (趋势跑起来后快速追踪)
    max_hold_bars=5,
    
    # === 区间策略参数 ===
    range_stop_atr=1.2,               # 区间紧止损
    range_take_profit_atr=1.8,        # 区间宽止盈
    range_trailing_atr=1.5,
    range_max_hold_bars=4,
    
    # === Attack策略 ===
    enable_attack_module=True,
    attack_min_score=3.5,
    attack_risk_per_trade=0.15,
    attack_max_positions=2,
    attack_stop_atr=1.0,
    attack_take_profit_atr=1.5,
    attack_trailing_atr=1.2,
    attack_max_hold_bars=2,
    attack_cooldown_bars=4,
    attack_loss_cooldown_bars=12,
    attack_volume_spike=1.6,
    attack_range_atr=0.9,
    attack_enabled_regimes=("uptrend", "downtrend", "transition", "range"),
    attack_breakout_enabled=True,
    attack_exhaustion_enabled=True,
    
    # === 其他模块关闭 ===
    enable_micro_momentum_module=True,
    enable_funding_module=True,
    funding_abs_rate_threshold=0.00005,
    funding_min_abs_ma=0.00002,
    enable_open_interest_module=True,
    enable_trade_flow_module=False,
    enable_order_book_module=False,
    enable_continuation_module=True,
    
    # === 冷却 (短) ===
    cooldown_bars=4,
    loss_cooldown_bars=12,
    time_exit_loss_cooldown_bars=24,
    early_failure_bars=0,
    early_failure_min_mfe_pct=0,
    early_failure_max_mae_pct=0,
    early_failure_reasons=(),
    
    # === 方向暂停 ===
    direction_loss_pause_bars=48,
    direction_loss_pause_pct=12.0,
    
    # === 反转保护 ===
    short_rebound_lookback_bars=96,
    short_rebound_block_pct=0.02,
    short_exhaustion_drop_pct=-0.06,
    long_flush_lookback_bars=96,
    long_flush_block_pct=-0.05,
    long_exhaustion_rise_pct=0.06,
    
    # === 区间策略参数 ===
    range_long_rsi_min=25.0,
    range_long_rsi_max=38.0,
    range_short_rsi_min=62.0,
    range_short_rsi_max=75.0,
    range_max_volume_ratio=1.8,
    range_long_max_body_pct=1.2,
    range_long_max_range_pct=1.2,
    range_long_max_trend_strength=0.15,
    range_short_max_trend_strength=-0.05,
    
    # === Transition策略 ===
    transition_long_enabled=True,
    transition_short_enabled=True,
    
    # === 自适应趋势 ===
    enable_adaptive_profiles=True,
    adaptive_trend_min_score=3.5,
    adaptive_trend_risk_per_trade=0.12,
    adaptive_trend_stop_atr=2.5,
    adaptive_trend_take_profit_atr=4.0,
    adaptive_trend_trailing_atr=1.8,
    adaptive_trend_max_hold_bars=8,
    adaptive_trend_allowed_regimes=("downtrend", "uptrend", "transition"),
    
    # === 允许的Regime (全部启用, 由策略选择器过滤) ===
    enabled_regimes=("uptrend", "downtrend", "transition", "range"),
    
    # === 信号过滤 ===
    min_score=2.5,
    invert_signals=False,
    
    # === Symbol选择器 ===
    selector_lookback_bars=96*14,
    selector_momentum_weight=45.0,
    selector_volatility_weight=180.0,
    selector_trend_weight=0.14,
    selector_noise_penalty=6.0,
    selector_min_avg_quote=200_000.0,
    selector_max_micro_noise=0.009,
    
    # === 杠杆 ===
    leverage_caps={
        "BTC-USDT-SWAP": SymbolRisk(max_leverage=50, min_notional=1.0),
        "ETH-USDT-SWAP": SymbolRisk(max_leverage=50, min_notional=1.0),
        "SOL-USDT-SWAP": SymbolRisk(max_leverage=40, min_notional=1.0),
        "BNB-USDT-SWAP": SymbolRisk(max_leverage=40, min_notional=1.0),
        "XRP-USDT-SWAP": SymbolRisk(max_leverage=30, min_notional=1.0),
        "DOGE-USDT-SWAP": SymbolRisk(max_leverage=30, min_notional=1.0),
        "ADA-USDT-SWAP": SymbolRisk(max_leverage=30, min_notional=1.0),
        "AVAX-USDT-SWAP": SymbolRisk(max_leverage=30, min_notional=1.0),
        "LINK-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
        "NEAR-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
        "SUI-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
        "ARB-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
        "OP-USDT-SWAP": SymbolRisk(max_leverage=25, min_notional=1.0),
        "INJ-USDT-SWAP": SymbolRisk(max_leverage=20, min_notional=1.0),
        "TIA-USDT-SWAP": SymbolRisk(max_leverage=20, min_notional=1.0),
    },
    
    # === Edge暂停 ===
    edge_lookback_trades=10,
    edge_pause_bars=12,
    symbol_edge_lookback_trades=1,
    symbol_edge_min_win_rate=1.0,
    symbol_edge_pause_bars=48,
    reason_edge_lookback_trades=7,
    reason_edge_min_win_rate=0.30,
    reason_edge_pause_bars=48,
    
    # === RiskManager ===
    rm_enabled=True,
    rm_max_single_position_pct=0.85,
    rm_max_total_position_pct=0.90,
    rm_max_daily_loss_pct=20.0,
    rm_max_weekly_loss_pct=40.0,
    rm_consecutive_loss_pause=4,
    rm_consecutive_loss_pause_bars=48,
    rm_volatility_halt_threshold=0.10,
    rm_min_liquidation_distance_pct=0.015,
    rm_pause_on_inconsistency=True,
    
    # === 验证窗口 ===
    windows_days=(30, 14, 7),
    min_bars=200,
)


# ============================================================
# Regime-aware 策略选择器 (核心创新)
# ============================================================
# 
# 原则: 基于市场结构选择策略, 不是历史表现
# 
# - uptrend:   只做 trend_long (顺势做多)
# - downtrend: 只做 trend_short (顺势做空)
# - range:     只做 range_revert (高抛低吸)
# - transition: 做 transition_breakout (突破)
#
# 这不是过拟合, 因为:
# 1. 趋势市做顺势是基本交易逻辑
# 2. 震荡市做反转是基本交易逻辑
# 3. 规则不依赖历史表现, 而是市场结构

REGIME_STRATEGY_MAP = {
    "uptrend": ["trend_long", "attack_breakout_long", "range_revert_long"],
    "downtrend": ["trend_short", "attack_breakout_short", "range_revert_short"],
    "range": ["range_revert_long", "range_revert_short", "attack_exhaustion_long", "attack_exhaustion_short"],
    "transition": ["transition_breakout_long", "transition_breakout_short"],
}

def should_trade_signal(sig_reason: str, regime: str) -> bool:
    """根据当前regime决定是否交易某个信号"""
    allowed = REGIME_STRATEGY_MAP.get(regime, [])
    return sig_reason in allowed
