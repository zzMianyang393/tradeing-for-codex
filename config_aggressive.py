"""
激进滚仓配置 — 10U → 500U / 30天目标

核心思路：
- 13.7% 日均复利 = 50x / 30天
- 15分钟K线，每天96根
- 8个策略模块全开，最大化信号密度
- 高杠杆(30-50x) + 激进仓位 + 严格止损
- 复利滚仓：每次盈利后本金增加，仓位自动放大

风险控制：
- 单笔最大亏损 ≤ 15% 本金
- 连亏4次暂停12小时
- 日亏损 > 25% 全天停止
- 回撤 > 50% 自动降级到保守模式
"""

from config import BacktestConfig, SymbolRisk
from dataclasses import replace


# ============================================================
# 第一阶段：10U → 50U (Day 1-10, 激进模式)
# ============================================================

AGGRESSIVE_CONFIG = BacktestConfig(
    # --- 起始资金 ---
    start_equity=10.0,
    
    # --- 时间框架 ---
    timeframe_minutes=15,  # 15分钟K线，信号密度最高
    
    # --- 费用 ---
    taker_fee=0.00005,  # OKX maker费率
    slippage=0.0003,    # 0.03%滑点估计
    
    # === 核心风控参数 ===
    risk_per_trade=0.35,           # 每笔风险35%本金 (10U本金→3.5U风险)
    max_margin_fraction=0.80,      # 单币种最大保证金占权益80%
    max_total_margin_fraction=0.70, # 总保证金占权益70%
    max_positions=3,               # 最多3个持仓
    active_symbol_limit=8,         # 监控8个币种
    
    # --- 防御模式(权益跌破60%启动) ---
    defensive_equity_fraction=0.60,
    defensive_risk_multiplier=0.50,  # 风险减半
    defensive_margin_fraction=0.30,
    
    # --- 盈利保护(权益超过起始120%启动) ---
    profit_lock_equity_fraction=1.20,
    profit_lock_risk_multiplier=0.60,
    profit_lock_margin_fraction=0.40,
    
    # --- 波动率目标 ---
    volatility_target_atr_pct=0.025,
    volatility_risk_floor=0.60,
    volatility_risk_power=0.80,
    
    # --- 单笔最大亏损占权益 ---
    max_trade_loss_pct_equity=15.0,
    
    # === 全部8个策略模块全开 ===
    
    # 1. 核心趋势/区间策略
    stop_atr=2.8,                    # 收紧止损，快速承认错误
    take_profit_atr=1.8,             # 放宽止盈，让利润跑
    trailing_atr=2.0,                # 移动止损跟随
    max_hold_bars=6,                 # 最大持仓6根K线(1.5小时)
    
    # 2. 区间反转策略
    range_stop_atr=2.0,
    range_take_profit_atr=0.8,
    range_trailing_atr=1.5,
    range_max_hold_bars=5,
    
    # 3. Attack突破策略(全开)
    enable_attack_module=True,
    attack_min_score=4.0,
    attack_risk_per_trade=0.20,      # attack仓位略小
    attack_max_positions=2,
    attack_stop_atr=1.2,             # 紧止损
    attack_take_profit_atr=1.5,
    attack_trailing_atr=1.4,
    attack_max_hold_bars=3,          # 3根K线快进快出
    attack_cooldown_bars=24,         # 攻击后冷却24根(6小时)
    attack_loss_cooldown_bars=96,    # 亏损后冷却24小时
    attack_volume_spike=1.8,         # 降低成交量门槛
    attack_range_atr=1.0,
    attack_enabled_regimes=("uptrend", "downtrend", "transition", "range"),
    attack_breakout_enabled=True,
    attack_exhaustion_enabled=True,
    
    # 4. Micro Momentum策略
    enable_micro_momentum_module=True,
    micro_momentum_min_volume_ratio=1.6,
    micro_momentum_min_body_atr=0.6,
    micro_momentum_risk_per_trade=0.15,
    micro_momentum_stop_atr=1.2,
    micro_momentum_take_profit_atr=1.0,
    micro_momentum_trailing_atr=1.0,
    micro_momentum_max_hold_bars=4,
    
    # 5. Funding策略
    enable_funding_module=True,
    funding_abs_rate_threshold=0.0004,
    funding_min_abs_ma=0.00015,
    funding_risk_per_trade=0.12,
    funding_stop_atr=1.8,
    funding_take_profit_atr=1.2,
    funding_trailing_atr=1.5,
    funding_max_hold_bars=10,
    
    # 6. Open Interest策略
    enable_open_interest_module=True,
    open_interest_min_change_pct=0.06,
    open_interest_min_volume_ratio=1.0,
    open_interest_risk_per_trade=0.12,
    open_interest_stop_atr=1.6,
    open_interest_take_profit_atr=1.3,
    open_interest_trailing_atr=1.5,
    open_interest_max_hold_bars=10,
    
    # 7. Trade Flow策略
    enable_trade_flow_module=True,
    trade_flow_min_imbalance=0.40,
    trade_flow_min_quote=400_000.0,
    trade_flow_risk_per_trade=0.12,
    trade_flow_stop_atr=1.4,
    trade_flow_take_profit_atr=1.1,
    trade_flow_trailing_atr=1.2,
    trade_flow_max_hold_bars=8,
    
    # 8. Order Book策略
    enable_order_book_module=True,
    order_book_min_depth_imbalance=0.25,
    order_book_max_spread_pct=0.006,
    order_book_risk_per_trade=0.12,
    order_book_stop_atr=1.4,
    order_book_take_profit_atr=1.1,
    order_book_trailing_atr=1.2,
    order_book_max_hold_bars=8,
    
    # === Continuation策略 ===
    enable_continuation_module=True,
    continuation_min_volume_ratio=1.3,
    continuation_min_trend_strength=1.0,
    continuation_risk_per_trade=0.15,
    continuation_stop_atr=2.0,
    continuation_take_profit_atr=1.5,
    continuation_trailing_atr=1.6,
    continuation_max_hold_bars=12,
    
    # === 冷却与保护 ===
    cooldown_bars=12,                 # 常规冷却3小时
    loss_cooldown_bars=48,            # 亏损后冷却12小时
    time_exit_loss_cooldown_bars=192, # 时间止损后冷却48小时
    early_failure_bars=4,             # 4根K线(1小时)内无盈利→退出
    early_failure_min_mfe_pct=0.001,  # 最小有利偏移0.1%
    early_failure_max_mae_pct=0.012,  # 最大不利偏移1.2%
    early_failure_reasons=("range_revert_long", "range_revert_short"),
    
    # === 方向性亏损暂停 ===
    direction_loss_pause_bars=192,   # 某方向大亏暂停48小时
    direction_loss_pause_pct=10.0,   # 单方向亏损10%触发
    
    # === 反转保护 ===
    short_rebound_lookback_bars=192,  # 3天回看
    short_rebound_block_pct=0.012,    # 反弹>1.2%阻止做空
    short_exhaustion_drop_pct=-0.05,  # 跌>5%视为耗尽
    long_flush_lookback_bars=192,
    long_flush_block_pct=-0.04,       # 跌>4%阻止做多
    long_exhaustion_rise_pct=0.05,    # 涨>5%视为耗尽
    
    # === 区间策略参数 ===
    range_long_rsi_min=25.0,
    range_long_rsi_max=38.0,
    range_short_rsi_min=62.0,
    range_short_rsi_max=75.0,
    range_max_volume_ratio=1.8,
    range_long_max_body_pct=1.2,
    range_long_max_range_pct=1.2,
    
    # === Transition策略 ===
    transition_long_enabled=True,
    transition_short_enabled=True,
    
    # === 自适应趋势(允许所有regime做趋势) ===
    enable_adaptive_profiles=True,
    adaptive_trend_min_score=3.5,
    adaptive_trend_risk_per_trade=0.10,
    adaptive_trend_stop_atr=2.0,
    adaptive_trend_take_profit_atr=1.2,
    adaptive_trend_trailing_atr=1.8,
    adaptive_trend_max_hold_bars=8,
    adaptive_trend_allowed_regimes=("downtrend", "uptrend", "transition"),
    
    # === 允许的Regime ===
    enabled_regimes=("uptrend", "downtrend", "transition", "range"),
    
    # === 信号过滤 ===
    min_score=2.8,           # 降低门槛，捕获更多信号
    invert_signals=False,
    
    # === Symbol选择器 ===
    selector_lookback_bars=96*14,  # 2周回看
    selector_momentum_weight=40.0, # 偏好高动量
    selector_volatility_weight=160.0, # 偏好高波动
    selector_trend_weight=0.15,
    selector_noise_penalty=6.0,    # 惩罚噪音币
    selector_min_avg_quote=300_000.0,
    selector_max_micro_noise=0.008,
    
    # === 杠杆配置(激进) ===
    leverage_caps={
        "BTC-USDT-SWAP": SymbolRisk(max_leverage=50, min_notional=2.0),
        "ETH-USDT-SWAP": SymbolRisk(max_leverage=50, min_notional=2.0),
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
    
    # === RiskManager(激进但不疯狂) ===
    rm_enabled=True,
    rm_max_single_position_pct=0.50,     # 单仓最大50%权益
    rm_max_total_position_pct=0.85,      # 总仓位最大85%权益
    rm_max_daily_loss_pct=25.0,          # 日亏损25%停止
    rm_max_weekly_loss_pct=40.0,         # 周亏损40%停止
    rm_consecutive_loss_pause=4,          # 连亏4次暂停
    rm_consecutive_loss_pause_bars=288,   # 暂停12小时(288根)
    rm_volatility_halt_threshold=0.08,   # ATR>8%暂停
    rm_min_liquidation_distance_pct=0.04,
    rm_pause_on_inconsistency=True,
    
    # === 验证窗口 ===
    windows_days=(30, 14, 7),
    min_bars=200,
)


# ============================================================
# 第二阶段：50U → 200U (Day 11-20, 适中模式)
# ============================================================

PHASE2_CONFIG = replace(
    AGGRESSIVE_CONFIG,
    start_equity=50.0,
    risk_per_trade=0.28,              # 降到28%
    max_margin_fraction=0.70,
    max_total_margin_fraction=0.60,
    max_positions=4,                  # 加到4仓
    min_score=3.0,                    # 提高门槛
    stop_atr=3.0,                     # 放宽止损(资金更大)
    take_profit_atr=2.0,
    trailing_atr=2.2,
    max_hold_bars=8,
    attack_min_score=4.5,
    attack_risk_per_trade=0.15,
    attack_stop_atr=1.5,
    attack_take_profit_atr=1.8,
    attack_max_hold_bars=4,
    cooldown_bars=16,
    loss_cooldown_bars=72,
    rm_max_daily_loss_pct=20.0,
    rm_consecutive_loss_pause=3,
    rm_consecutive_loss_pause_bars=384,  # 暂停16小时
)


# ============================================================
# 第三阶段：200U → 500U (Day 21-30, 稳健模式)
# ============================================================

PHASE3_CONFIG = replace(
    PHASE2_CONFIG,
    start_equity=200.0,
    risk_per_trade=0.22,              # 降到22%
    max_margin_fraction=0.60,
    max_total_margin_fraction=0.50,
    max_positions=3,                  # 回到3仓(资金大了要保守)
    min_score=3.2,
    stop_atr=3.2,
    take_profit_atr=2.2,
    trailing_atr=2.5,
    max_hold_bars=10,
    attack_min_score=5.0,
    attack_risk_per_trade=0.10,
    attack_stop_atr=1.8,
    attack_take_profit_atr=2.0,
    attack_max_hold_bars=5,
    cooldown_bars=20,
    loss_cooldown_bars=96,
    rm_max_daily_loss_pct=15.0,
    rm_max_weekly_loss_pct=30.0,
    rm_consecutive_loss_pause=3,
    rm_consecutive_loss_pause_bars=576,  # 暂停24小时
)


# ============================================================
# 阶段选择器
# ============================================================

def get_config_for_equity(equity: float) -> BacktestConfig:
    """根据当前权益自动选择阶段配置"""
    if equity < 50.0:
        return AGGRESSIVE_CONFIG      # 10-50U: 激进
    elif equity < 200.0:
        return PHASE2_CONFIG          # 50-200U: 适中
    else:
        return PHASE3_CONFIG          # 200-500U: 稳健
