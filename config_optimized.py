"""
10U → 500U 滚仓配置 (最终优化版)

基于回测诊断结果：
- trend_long 是最赚钱的策略 (+0.72, 41.2% WR)
- range_revert_short 也不错 (66.7% WR)
- attack和micro_momentum策略在当前市场亏损
- short策略整体亏损(除range_revert_short外)
- 风控太严导致9649次拒绝，只有56笔成交

优化方向：
1. 只保留盈利策略：trend_long + range_revert
2. 禁用亏损策略：attack + micro_momentum
3. 大幅放宽风控：允许更多交易
4. 激进仓位：每笔20%本金
5. 复利滚仓：盈利后自动加仓
"""

from config import BacktestConfig, SymbolRisk


OPTIMIZED_AGGRESSIVE = BacktestConfig(
    # === 起始资金 ===
    start_equity=10.0,
    
    # === 时间框架 ===
    timeframe_minutes=15,
    
    # === 费用 ===
    taker_fee=0.00005,
    slippage=0.0003,
    
    # === 核心风控(激进) ===
    risk_per_trade=0.25,              # 每笔25%本金
    max_margin_fraction=0.80,         # 单币最大80%
    max_total_margin_fraction=0.70,   # 总仓位70%
    max_positions=3,                  # 最多3仓
    active_symbol_limit=8,
    
    # === 防御模式 ===
    defensive_equity_fraction=0.60,
    defensive_risk_multiplier=0.50,
    defensive_margin_fraction=0.30,
    
    # === 盈利保护 ===
    profit_lock_equity_fraction=1.30,
    profit_lock_risk_multiplier=0.65,
    profit_lock_margin_fraction=0.45,
    
    # === 波动率目标 ===
    volatility_target_atr_pct=0.025,
    volatility_risk_floor=0.60,
    volatility_risk_power=0.80,
    
    # === 单笔最大亏损 ===
    max_trade_loss_pct_equity=12.0,
    
    # === 趋势策略(核心盈利策略) ===
    stop_atr=2.5,                     # 止损
    take_profit_atr=2.5,              # 止盈(1:1 R:R)
    trailing_atr=2.2,                 # 移动止损
    max_hold_bars=8,                  # 最大持仓2小时
    
    # === 区间策略(辅助盈利) ===
    range_stop_atr=1.8,
    range_take_profit_atr=1.2,
    range_trailing_atr=1.6,
    range_max_hold_bars=6,
    
    # === 禁用亏损策略 ===
    enable_attack_module=False,        # 攻击策略亏损
    enable_micro_momentum_module=False, # 微动量亏损
    enable_funding_module=False,
    enable_open_interest_module=False,
    enable_trade_flow_module=False,
    enable_order_book_module=False,
    enable_continuation_module=False,
    
    # === 信号过滤 ===
    min_score=2.5,                    # 降低门槛
    invert_signals=False,
    
    # === 冷却(极短) ===
    cooldown_bars=8,                  # 2小时
    loss_cooldown_bars=24,            # 6小时
    time_exit_loss_cooldown_bars=48,  # 12小时
    early_failure_bars=0,             # 禁用early failure
    early_failure_min_mfe_pct=0,
    early_failure_max_mae_pct=0,
    early_failure_reasons=(),
    
    # === 方向暂停(宽松) ===
    direction_loss_pause_bars=96,     # 24小时(从192降到96)
    direction_loss_pause_pct=15.0,    # 15%亏损才暂停(从10%提高)
    
    # === 反转保护(宽松) ===
    short_rebound_lookback_bars=96,   # 24小时(从192降到96)
    short_rebound_block_pct=0.02,     # 2%反弹才阻止(从1.2%放宽)
    short_exhaustion_drop_pct=-0.06,
    long_flush_lookback_bars=96,
    long_flush_block_pct=-0.05,       # 5%下跌才阻止(从4%放宽)
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
    adaptive_trend_stop_atr=2.2,
    adaptive_trend_take_profit_atr=2.0,
    adaptive_trend_trailing_atr=2.0,
    adaptive_trend_max_hold_bars=8,
    adaptive_trend_allowed_regimes=('downtrend', 'uptrend', 'transition'),
    
    # === 允许的Regime ===
    enabled_regimes=('uptrend', 'downtrend', 'transition', 'range'),
    
    # === Symbol选择器(高波动偏好) ===
    selector_lookback_bars=96*7,
    selector_momentum_weight=50.0,
    selector_volatility_weight=200.0,
    selector_trend_weight=0.12,
    selector_noise_penalty=5.0,
    selector_min_avg_quote=150_000.0,
    selector_max_micro_noise=0.01,
    
    # === 杠杆(激进) ===
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
    },
    
    # === RiskManager(宽松) ===
    rm_enabled=True,
    rm_max_single_position_pct=0.85,    # 单仓85%
    rm_max_total_position_pct=0.90,     # 总仓90%
    rm_max_daily_loss_pct=35.0,         # 日亏35%停止
    rm_max_weekly_loss_pct=55.0,        # 周亏55%停止
    rm_consecutive_loss_pause=5,        # 连亏5次暂停
    rm_consecutive_loss_pause_bars=144, # 暂停36小时
    rm_volatility_halt_threshold=0.15,  # ATR>15%暂停
    rm_min_liquidation_distance_pct=0.03,
    rm_pause_on_inconsistency=True,
    
    # === 验证窗口 ===
    windows_days=(365, 180, 90, 60, 30, 14, 7),
    min_bars=200,
)


# ============================================================
# 阶段配置
# ============================================================

def get_phase_config(phase: int) -> BacktestConfig:
    """获取阶段配置: 1=激进, 2=适中, 3=稳健"""
    from dataclasses import replace
    
    if phase == 1:
        return OPTIMIZED_AGGRESSIVE
    
    elif phase == 2:
        return replace(
            OPTIMIZED_AGGRESSIVE,
            start_equity=50.0,
            risk_per_trade=0.20,
            max_margin_fraction=0.70,
            max_total_margin_fraction=0.60,
            max_positions=4,
            min_score=2.8,
            stop_atr=2.8,
            take_profit_atr=2.8,
            trailing_atr=2.5,
            max_hold_bars=10,
            cooldown_bars=12,
            loss_cooldown_bars=36,
            rm_max_daily_loss_pct=25.0,
            rm_consecutive_loss_pause=4,
            rm_consecutive_loss_pause_bars=192,
        )
    
    else:  # phase 3
        return replace(
            get_phase_config(2),
            start_equity=200.0,
            risk_per_trade=0.15,
            max_margin_fraction=0.60,
            max_total_margin_fraction=0.50,
            max_positions=3,
            min_score=3.0,
            stop_atr=3.0,
            take_profit_atr=3.0,
            trailing_atr=2.8,
            max_hold_bars=12,
            cooldown_bars=16,
            loss_cooldown_bars=48,
            rm_max_daily_loss_pct=18.0,
            rm_max_weekly_loss_pct=35.0,
            rm_consecutive_loss_pause=3,
            rm_consecutive_loss_pause_bars=288,
        )
