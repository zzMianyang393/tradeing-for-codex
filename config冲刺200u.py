"""
冲刺配置: 10U → 200U / 30天
基于aggressive config + 诊断修复

核心思路:
- 高风险(25-30%) + 高杠杆(40-50x) + 紧止损(1.5 ATR)
- 日均复利10.5% = 20x/30天
- 每笔目标+2.5%净收益
- 严格风控: 单笔最大亏损8%, 连亏暂停
"""

from config import BacktestConfig, SymbolRisk


SPRINT_200U = BacktestConfig(
    # === 起始资金 ===
    start_equity=10.0,
    
    # === 时间框架 ===
    timeframe_minutes=15,
    
    # === 费用 ===
    taker_fee=0.00005,
    slippage=0.0003,
    
    # === 核心风控 (激进) ===
    risk_per_trade=0.28,              # 每笔28%本金
    max_margin_fraction=0.85,         # 单币最大85%
    max_total_margin_fraction=0.75,   # 总仓位75%
    max_positions=3,                  # 最多3仓
    active_symbol_limit=8,            # 监控8个币种
    
    # === 防御模式 (权益跌破50%启动) ===
    defensive_equity_fraction=0.50,
    defensive_risk_multiplier=0.40,   # 风险降到40%
    defensive_margin_fraction=0.25,
    
    # === 盈利保护 (权益超过起始150%启动) ===
    profit_lock_equity_fraction=1.50,
    profit_lock_risk_multiplier=0.60,
    profit_lock_margin_fraction=0.50,
    
    # === 波动率目标 ===
    volatility_target_atr_pct=0.025,
    volatility_risk_floor=0.50,       # 更激进
    volatility_risk_power=0.80,
    
    # === 单笔最大亏损 ===
    max_trade_loss_pct_equity=8.0,    # 严格限制8%
    
    # === 趋势策略 (核心) ===
    stop_atr=1.5,                     # 紧止损, 快速认错
    take_profit_atr=2.5,              # 宽止盈, 让利润跑
    trailing_atr=1.8,                 # 移动止损
    max_hold_bars=6,                  # 最大持仓1.5小时
    
    # === 区间策略 ===
    range_stop_atr=1.2,
    range_take_profit_atr=1.8,
    range_trailing_atr=1.4,
    range_max_hold_bars=6,
    
    # === Attack策略 (开启) ===
    enable_attack_module=True,
    attack_min_score=3.5,
    attack_risk_per_trade=0.18,       # attack仓位略小
    attack_max_positions=2,
    attack_stop_atr=1.0,              # 紧止损
    attack_take_profit_atr=1.8,
    attack_trailing_atr=1.2,
    attack_max_hold_bars=3,           # 3根K线快进快出
    attack_cooldown_bars=6,           # 攻击后冷却1.5小时
    attack_loss_cooldown_bars=24,     # 亏损后冷却6小时
    attack_volume_spike=1.6,          # 降低成交量门槛
    attack_range_atr=0.9,
    attack_enabled_regimes=("uptrend", "downtrend", "transition", "range"),
    attack_breakout_enabled=True,
    attack_exhaustion_enabled=True,
    
    # === Micro Momentum (关闭 - 亏损策略) ===
    enable_micro_momentum_module=False,
    
    # === Funding (关闭) ===
    enable_funding_module=False,
    
    # === Open Interest (关闭) ===
    enable_open_interest_module=False,
    
    # === Trade Flow (关闭) ===
    enable_trade_flow_module=False,
    
    # === Order Book (关闭) ===
    enable_order_book_module=False,
    
    # === Continuation (关闭) ===
    enable_continuation_module=False,
    
    # === 冷却 (极短) ===
    cooldown_bars=4,                  # 1小时
    loss_cooldown_bars=12,            # 3小时
    time_exit_loss_cooldown_bars=24,  # 6小时
    early_failure_bars=0,             # 禁用early failure
    early_failure_min_mfe_pct=0,
    early_failure_max_mae_pct=0,
    early_failure_reasons=(),
    
    # === 方向暂停 (宽松) ===
    direction_loss_pause_bars=48,     # 12小时
    direction_loss_pause_pct=12.0,    # 12%亏损才暂停
    
    # === 反转保护 (宽松) ===
    short_rebound_lookback_bars=96,   # 24小时
    short_rebound_block_pct=0.02,     # 2%反弹才阻止
    short_exhaustion_drop_pct=-0.06,
    long_flush_lookback_bars=96,
    long_flush_block_pct=-0.05,       # 5%下跌才阻止
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
    adaptive_trend_stop_atr=1.8,
    adaptive_trend_take_profit_atr=2.0,
    adaptive_trend_trailing_atr=1.6,
    adaptive_trend_max_hold_bars=8,
    adaptive_trend_allowed_regimes=("downtrend", "uptrend", "transition"),
    
    # === 允许的Regime ===
    enabled_regimes=("uptrend", "downtrend", "transition", "range"),
    
    # === 信号过滤 ===
    min_score=2.5,                    # 降低门槛
    invert_signals=False,
    
    # === Symbol选择器 ===
    selector_lookback_bars=96*14,     # 2周回看
    selector_momentum_weight=45.0,    # 偏好高动量
    selector_volatility_weight=180.0, # 偏好高波动
    selector_trend_weight=0.14,
    selector_noise_penalty=6.0,       # 惩罚噪音币
    selector_min_avg_quote=200_000.0,
    selector_max_micro_noise=0.009,
    
    # === 杠杆 (激进) ===
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
    
    # === Edge暂停 (宽松) ===
    edge_lookback_trades=10,
    edge_pause_bars=12,               # 3小时
    symbol_edge_lookback_trades=1,
    symbol_edge_min_win_rate=1.0,
    symbol_edge_pause_bars=48,        # 12小时
    reason_edge_lookback_trades=7,
    reason_edge_min_win_rate=0.30,
    reason_edge_pause_bars=48,        # 12小时
    
    # === RiskManager (宽松) ===
    rm_enabled=True,
    rm_max_single_position_pct=0.85,  # 单仓85%
    rm_max_total_position_pct=0.90,   # 总仓90%
    rm_max_daily_loss_pct=20.0,       # 日亏20%停止
    rm_max_weekly_loss_pct=40.0,      # 周亏40%停止
    rm_consecutive_loss_pause=4,      # 连亏4次暂停
    rm_consecutive_loss_pause_bars=48, # 暂停12小时
    rm_volatility_halt_threshold=0.10, # ATR>10%暂停
    rm_min_liquidation_distance_pct=0.015,
    rm_pause_on_inconsistency=True,
    
    # === 验证窗口 ===
    windows_days=(30, 14, 7),
    min_bars=200,
)
