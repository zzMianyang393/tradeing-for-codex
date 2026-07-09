"""
Balanced Optimized v2 — 基于交易诊断的深度修复

v1诊断:
- range_revert: 7/8 wins, +4.65 (核心盈利)
- trend_long: 3/7 wins, -1.18 (亏损来源)
- trend_short(180d): 4/9 wins, -2.14 (亏损来源)
- NEAR: 10 trades, net +0.25 (过度交易, 大亏损)
- ADA: 单笔-1.30 (风险过高)

v2修复:
1. 收紧趋势止损 (2.8→2.0) — 减少单笔亏损幅度
2. 提高min_score (2.5→3.0) — 过滤低质量趋势信号
3. 降低risk_per_trade (0.20→0.15) — 限制单笔风险
4. 启用attack模块 — 增加信号多样性
5. 缩短max_hold_bars (8→6) — 减少时间止损亏损
6. 调整take_profit (2.0→1.5) — 更快锁定利润
"""

from config import BacktestConfig, SymbolRisk


BALANCED_OPTIMIZED_V2 = BacktestConfig(
    # === 起始资金 ===
    start_equity=10.0,

    # === 时间框架 ===
    timeframe_minutes=15,

    # === 费用 ===
    taker_fee=0.00005,
    slippage=0.0003,

    # === 核心风控(更保守) ===
    risk_per_trade=0.15,              # 从0.20降到0.15
    max_margin_fraction=0.65,
    max_total_margin_fraction=0.55,
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
    max_trade_loss_pct_equity=12.0,   # 从15降到12

    # === 趋势策略参数(收紧止损) ===
    stop_atr=2.0,                     # 从2.8收紧到2.0
    take_profit_atr=1.5,              # 从2.0降到1.5 (更快止盈)
    trailing_atr=1.8,                 # 从2.2降到1.8
    max_hold_bars=6,                  # 从8降到6 (减少时间止损)

    # === 区间策略参数(保持v1) ===
    range_stop_atr=2.0,
    range_take_profit_atr=1.0,
    range_trailing_atr=1.6,
    range_max_hold_bars=6,

    # === Attack模块(启用) ===
    enable_attack_module=True,        # 启用, 增加信号多样性
    attack_min_score=4.0,             # 从4.5降到4.0
    attack_risk_per_trade=0.10,       # attack仓位较小
    attack_max_positions=2,
    attack_stop_atr=1.2,              # 紧止损
    attack_take_profit_atr=1.0,
    attack_trailing_atr=1.3,
    attack_max_hold_bars=3,           # 快进快出
    attack_cooldown_bars=24,
    attack_loss_cooldown_bars=96,
    attack_volume_spike=1.8,          # 从2.2降到1.8
    attack_range_atr=1.0,             # 从1.7降到1.0
    attack_enabled_regimes=('uptrend', 'downtrend', 'transition', 'range'),
    attack_breakout_enabled=True,
    attack_exhaustion_enabled=True,

    # === 其他模块(关闭) ===
    enable_micro_momentum_module=False,
    enable_continuation_module=False,
    enable_funding_module=False,
    enable_open_interest_module=False,
    enable_trade_flow_module=False,
    enable_order_book_module=False,

    # === 信号过滤(提高门槛) ===
    min_score=3.0,                    # 从2.5提高到3.0
    invert_signals=False,

    # === 冷却(保持v1) ===
    cooldown_bars=12,
    loss_cooldown_bars=48,
    time_exit_loss_cooldown_bars=96,
    early_failure_bars=0,
    early_failure_min_mfe_pct=0,
    early_failure_max_mae_pct=0,
    early_failure_reasons=(),

    # === 方向暂停 ===
    direction_loss_pause_bars=192,
    direction_loss_pause_pct=15.0,

    # === 反转保护 ===
    short_rebound_lookback_bars=144,
    short_rebound_block_pct=0.02,
    short_rebound_rsi_floor=48.0,
    short_exhaustion_drop_pct=-0.06,
    short_exhaustion_rsi_ceiling=46.0,
    short_exhaustion_volume_ratio=2.4,
    long_flush_lookback_bars=144,
    long_flush_block_pct=-0.045,
    long_flush_rsi_ceiling=52.0,
    long_exhaustion_rise_pct=0.06,
    long_exhaustion_rsi_floor=54.0,
    long_exhaustion_volume_ratio=2.4,

    # === 区间策略参数(保持v1) ===
    range_long_rsi_min=22.0,
    range_long_rsi_max=38.0,
    range_short_rsi_min=62.0,
    range_short_rsi_max=75.0,
    range_max_volume_ratio=1.8,
    range_long_max_body_pct=1.2,
    range_long_max_range_pct=1.2,
    range_short_min_move_1d=-1.0,
    range_long_max_trend_strength=0.12,
    range_short_max_trend_strength=-0.05,

    # === Transition策略 ===
    transition_long_enabled=True,
    transition_short_enabled=True,
    transition_long_min_move_21d=-1.0,

    # === 允许的Regime ===
    enabled_regimes=('uptrend', 'downtrend', 'transition', 'range'),

    # === 自适应趋势(保持v1) ===
    enable_adaptive_profiles=True,
    adaptive_trend_min_score=3.2,
    adaptive_trend_risk_per_trade=0.12,
    adaptive_trend_stop_atr=2.0,      # 从2.4收紧到2.0
    adaptive_trend_take_profit_atr=1.5,
    adaptive_trend_trailing_atr=1.8,
    adaptive_trend_max_hold_bars=6,   # 从8降到6
    adaptive_trend_allowed_regimes=('downtrend', 'uptrend', 'transition'),

    # === Symbol选择器 ===
    selector_lookback_bars=96*14,
    selector_momentum_weight=40.0,
    selector_volatility_weight=180.0,
    selector_trend_weight=0.12,
    selector_noise_penalty=6.0,
    selector_min_avg_quote=200_000.0,
    selector_max_micro_noise=0.009,

    # === Symbol Edge ===
    edge_lookback_trades=10,
    edge_pause_bars=288,
    symbol_edge_lookback_trades=5,
    symbol_edge_min_win_rate=0.5,
    symbol_edge_pause_bars=576,

    reason_edge_lookback_trades=7,
    reason_edge_min_win_rate=0.34,
    reason_edge_pause_bars=576,

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

    # === RiskManager ===
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
