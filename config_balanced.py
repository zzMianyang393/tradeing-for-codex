"""
Balanced Optimized Config — 基于诊断分析的修复版

诊断结论:
- 默认配置: 5笔交易, 0%胜率, 风控死亡螺旋
- 根因: 冷却期连锁反应 + regime限制 + symbol_edge过严

本配置修复:
1. 开启所有4个regime (含趋势跟踪)
2. 大幅降低冷却期 (从240-2880降到48-576)
3. 启用transition_long
4. 降低min_score到2.5
5. 禁用early_failure
6. symbol_edge_min_win_rate从100%降到50%
7. 放宽reversal block阈值
8. 适中仓位 (20% per trade)
"""

from config import BacktestConfig, SymbolRisk


BALANCED_OPTIMIZED = BacktestConfig(
    # === 起始资金 ===
    start_equity=10.0,

    # === 时间框架 ===
    timeframe_minutes=15,

    # === 费用 ===
    taker_fee=0.00005,
    slippage=0.0003,

    # === 核心风控(适中) ===
    risk_per_trade=0.20,
    max_margin_fraction=0.70,
    max_total_margin_fraction=0.60,
    max_positions=3,
    active_symbol_limit=8,

    # === 防御模式 ===
    defensive_equity_fraction=0.65,
    defensive_risk_multiplier=0.55,
    defensive_margin_fraction=0.35,

    # === 盈利保护 ===
    profit_lock_equity_fraction=1.25,
    profit_lock_risk_multiplier=0.60,
    profit_lock_margin_fraction=0.40,

    # === 波动率目标 ===
    volatility_target_atr_pct=0.025,
    volatility_risk_floor=0.65,
    volatility_risk_power=0.80,

    # === 单笔最大亏损 ===
    max_trade_loss_pct_equity=15.0,

    # === 趋势策略参数 ===
    stop_atr=2.8,
    take_profit_atr=2.0,
    trailing_atr=2.2,
    max_hold_bars=8,

    # === 区间策略参数 ===
    range_stop_atr=2.0,
    range_take_profit_atr=1.0,
    range_trailing_atr=1.6,
    range_max_hold_bars=6,

    # === 冷却(大幅放宽) ===
    cooldown_bars=12,                 # 原24, 降一半
    loss_cooldown_bars=48,            # 原240, 降5倍
    time_exit_loss_cooldown_bars=96,  # 原288, 降3倍
    early_failure_bars=0,             # 原5, 禁用
    early_failure_min_mfe_pct=0,
    early_failure_max_mae_pct=0,
    early_failure_reasons=(),

    # === 方向暂停(放宽) ===
    direction_loss_pause_bars=192,    # 原480, 降2.5倍
    direction_loss_pause_pct=15.0,    # 原12%, 提高门槛

    # === 反转保护(放宽, 减少与range-revert的矛盾) ===
    short_rebound_lookback_bars=144,  # 原288, 缩短
    short_rebound_block_pct=0.02,     # 原1.5%, 放宽
    short_rebound_rsi_floor=48.0,
    short_exhaustion_drop_pct=-0.06,
    short_exhaustion_rsi_ceiling=46.0,
    short_exhaustion_volume_ratio=2.4,
    long_flush_lookback_bars=144,     # 原288, 缩短
    long_flush_block_pct=-0.045,
    long_flush_rsi_ceiling=52.0,
    long_exhaustion_rise_pct=0.06,
    long_exhaustion_rsi_floor=54.0,
    long_exhaustion_volume_ratio=2.4,

    # === 区间策略参数(放宽RSI窗口) ===
    range_long_rsi_min=22.0,          # 原27
    range_long_rsi_max=38.0,          # 原37
    range_short_rsi_min=62.0,         # 原64
    range_short_rsi_max=75.0,         # 原73
    range_max_volume_ratio=1.8,       # 原1.7
    range_long_max_body_pct=1.2,      # 原1.0
    range_long_max_range_pct=1.2,     # 原1.0
    range_short_min_move_1d=-1.0,
    range_long_max_trend_strength=0.12,  # 原0.10
    range_short_max_trend_strength=-0.05,

    # === Transition策略 ===
    transition_long_enabled=True,     # 原False
    transition_short_enabled=True,
    transition_long_min_move_21d=-1.0,

    # === 允许的Regime(开启全部4个) ===
    enabled_regimes=('uptrend', 'downtrend', 'transition', 'range'),

    # === 自适应趋势(修复死代码) ===
    enable_adaptive_profiles=True,
    adaptive_trend_min_score=3.2,     # 原3.7(不可能), 降到3.2
    adaptive_trend_risk_per_trade=0.12,
    adaptive_trend_stop_atr=2.4,
    adaptive_trend_take_profit_atr=1.5,
    adaptive_trend_trailing_atr=2.0,
    adaptive_trend_max_hold_bars=8,
    adaptive_trend_allowed_regimes=('downtrend', 'uptrend', 'transition'),

    # === 信号过滤 ===
    min_score=2.5,                    # 原3.25
    invert_signals=False,

    # === Symbol选择器 ===
    selector_lookback_bars=96*14,
    selector_momentum_weight=40.0,
    selector_volatility_weight=180.0,
    selector_trend_weight=0.12,
    selector_noise_penalty=6.0,       # 原9
    selector_min_avg_quote=200_000.0, # 原250k
    selector_max_micro_noise=0.009,   # 原0.0072

    # === Symbol Edge(修复) ===
    edge_lookback_trades=10,
    edge_pause_bars=288,
    symbol_edge_lookback_trades=5,    # 原1
    symbol_edge_min_win_rate=0.5,     # 原1.0(不可能)
    symbol_edge_pause_bars=576,       # 原2880(30天!)

    reason_edge_lookback_trades=7,
    reason_edge_min_win_rate=0.34,
    reason_edge_pause_bars=576,       # 原1152(8天)

    # === Target Window配置 ===
    enable_target_window_profiles=True,
    target_window_excluded_symbols=('XRP-USDT-SWAP', 'BNB-USDT-SWAP', 'SUI-USDT-SWAP'),
    target_180_excluded_symbols=('XRP-USDT-SWAP', 'BNB-USDT-SWAP', 'SUI-USDT-SWAP', 'UNI-USDT-SWAP'),
    target_long_window_preferred_symbols=('ADA-USDT-SWAP', 'AVAX-USDT-SWAP', 'NEAR-USDT-SWAP', 'ARB-USDT-SWAP'),
    long_window_days=365,
    long_window_symbol_limit=5,
    short_window_days=30,
    short_window_symbol_limit=10,
    long_window_preferred_symbols=(),

    # === RiskManager(适中) ===
    rm_enabled=True,
    rm_max_single_position_pct=0.50,
    rm_max_total_position_pct=0.80,
    rm_max_daily_loss_pct=25.0,
    rm_max_weekly_loss_pct=40.0,
    rm_consecutive_loss_pause=4,
    rm_consecutive_loss_pause_bars=288,
    rm_volatility_halt_threshold=0.08,
    rm_max_order_book_spread_pct=0.0,
    rm_min_order_book_depth_quote=0.0,
    rm_min_liquidation_distance_pct=0.04,
    rm_pause_on_inconsistency=True,

    # === 杠杆 ===
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
        "FIL-USDT-SWAP": SymbolRisk(max_leverage=15, min_notional=1.0),
    },

    # === 验证窗口 ===
    windows_days=(365, 180, 90, 60, 30, 14, 7),
    min_bars=200,
)
