from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SymbolRisk:
    max_leverage: float
    min_notional: float = 5.0


@dataclass(frozen=True)
class BacktestConfig:
    start_equity: float = 10.0
    timeframe_minutes: int = 15
    taker_fee: float = 0.00005
    slippage: float = 0.0
    risk_per_trade: float = 0.13
    max_margin_fraction: float = 0.65
    max_total_margin_fraction: float = 0.55
    defensive_equity_fraction: float = 0.80
    defensive_risk_multiplier: float = 0.65
    defensive_margin_fraction: float = 0.35
    profit_lock_equity_fraction: float = 1.25
    profit_lock_risk_multiplier: float = 0.55
    profit_lock_margin_fraction: float = 0.35
    volatility_target_atr_pct: float = 0.022
    volatility_risk_floor: float = 0.75
    volatility_risk_power: float = 0.75
    max_trade_loss_pct_equity: float = 8.0
    bearish_range_long_risk_multiplier: float = 1.0
    bullish_range_short_risk_multiplier: float = 1.0
    symbol_risk_multipliers: dict[str, float] = field(
        default_factory=lambda: {}
    )
    reason_risk_multipliers: dict[str, float] = field(
        default_factory=lambda: {
            "range_revert_long": 0.85,
            "range_revert_short": 0.85,
        }
    )
    allowed_symbols: tuple[str, ...] = ()
    excluded_symbols: tuple[str, ...] = ()
    max_positions: int = 2
    active_symbol_limit: int = 6
    short_window_symbol_limit: int = 10
    short_window_days: int = 30
    selector_lookback_bars: int = 96 * 21
    selector_momentum_weight: float = 32.0
    selector_volatility_weight: float = 140.0
    selector_trend_weight: float = 0.12
    selector_noise_penalty: float = 9.0
    selector_min_avg_quote: float = 250_000.0
    selector_max_micro_noise: float = 0.0072
    stop_atr: float = 2.8
    take_profit_atr: float = 1.8
    trailing_atr: float = 2.34
    max_hold_bars: int = 8
    range_stop_atr: float = 2.0
    range_take_profit_atr: float = 0.85
    range_trailing_atr: float = 1.56
    range_max_hold_bars: int = 8
    defensive_range_exit_equity_fraction: float = 1.1
    defensive_range_take_profit_atr: float = 0.65
    cooldown_bars: int = 24
    loss_cooldown_bars: int = 48
    time_exit_loss_cooldown_bars: int = 96
    early_failure_bars: int = 0
    early_failure_min_mfe_pct: float = 0.002
    early_failure_max_mae_pct: float = 0.016
    early_failure_reasons: tuple[str, ...] = ("range_revert_long", "range_revert_short")
    direction_loss_pause_bars: int = 192
    direction_loss_pause_pct: float = 15.0
    short_rebound_lookback_bars: int = 96 * 3
    short_rebound_block_pct: float = 0.015
    short_rebound_rsi_floor: float = 48.0
    short_exhaustion_drop_pct: float = -0.06
    short_exhaustion_rsi_ceiling: float = 46.0
    short_exhaustion_volume_ratio: float = 2.4
    long_flush_lookback_bars: int = 96 * 3
    long_flush_block_pct: float = -0.045
    long_flush_rsi_ceiling: float = 52.0
    long_exhaustion_rise_pct: float = 0.06
    long_exhaustion_rsi_floor: float = 54.0
    long_exhaustion_volume_ratio: float = 2.4
    range_long_rsi_min: float = 27.0
    range_long_rsi_max: float = 37.0
    range_short_rsi_min: float = 64.0
    range_short_rsi_max: float = 73.0
    range_max_volume_ratio: float = 1.7
    range_long_max_body_pct: float = 1.0
    range_long_max_range_pct: float = 1.0
    range_short_min_move_1d: float = -1.0
    range_long_max_trend_strength: float = 0.1
    range_short_max_trend_strength: float = -0.05
    transition_long_enabled: bool = True
    transition_short_enabled: bool = True
    transition_long_min_move_21d: float = -1.0
    transition_long_pullback_min_volume_ratio: float = 1.3
    transition_long_pullback_rsi_min: float = 45.0
    transition_long_pullback_rsi_max: float = 62.0
    transition_long_pullback_max_move_21d_abs: float = 0.12
    transition_long_pullback_min_trend_strength: float = 0.5
    transition_long_volume_min_volume_ratio: float = 1.35
    transition_long_volume_rsi_max: float = 65.0
    transition_long_volume_min_trend_strength: float = 0.5
    transition_long_volume_min_body_atr: float = 0.25
    transition_long_volume_max_upper_shadow_body: float = 1.5
    transition_long_consolidation_enabled: bool = False
    transition_long_consolidation_lookback_bars: int = 8
    transition_long_consolidation_max_range_atr: float = 1.0
    transition_long_consolidation_min_volume_ratio: float = 1.15
    transition_long_consolidation_max_avg_volume_ratio: float = 1.0
    transition_long_consolidation_rsi_max: float = 64.0
    transition_long_consolidation_min_trend_strength: float = 0.5
    transition_long_consolidation_min_body_atr: float = 0.25
    # Regime classification thresholds (configurable for wider transition band)
    regime_uptrend_threshold: float = 1.2
    regime_downtrend_threshold: float = -1.2
    regime_range_strength_max: float = 0.9
    regime_range_atr_pct_max: float = 0.0045
    enable_target_window_profiles: bool = True
    target_window_excluded_symbols: tuple[str, ...] = (
        "XRP-USDT-SWAP",
        "BNB-USDT-SWAP",
        "SUI-USDT-SWAP",
    )
    target_180_excluded_symbols: tuple[str, ...] = (
        "XRP-USDT-SWAP",
        "BNB-USDT-SWAP",
        "SUI-USDT-SWAP",
        "UNI-USDT-SWAP",
        "SOL-USDT-SWAP",
        "LINK-USDT-SWAP",
    )
    target_long_window_preferred_symbols: tuple[str, ...] = (
        "ADA-USDT-SWAP",
        "AVAX-USDT-SWAP",
        "NEAR-USDT-SWAP",
        "ARB-USDT-SWAP",
        "SUI-USDT-SWAP",
        "INJ-USDT-SWAP",
    )
    long_window_days: int = 365
    long_window_symbol_limit: int = 5
    enable_long_window_aggressive_profile: bool = False
    long_window_aggressive_cooldown_bars: int = 12
    long_window_aggressive_max_margin_fraction: float = 1.0
    long_window_aggressive_max_total_margin_fraction: float = 0.85
    long_window_aggressive_leverage: float = 30.0
    long_window_preferred_symbols: tuple[str, ...] = ()
    min_score: float = 2.5
    edge_lookback_trades: int = 10
    edge_pause_bars: int = 48
    symbol_edge_lookback_trades: int = 1
    symbol_edge_min_win_rate: float = 1.0
    symbol_edge_pause_bars: int = 96 * 2
    reason_edge_lookback_trades: int = 7
    reason_edge_min_win_rate: float = 0.34
    reason_edge_pause_bars: int = 192
    invert_signals: bool = False
    enabled_regimes: tuple[str, ...] = ("uptrend", "downtrend", "transition", "range")
    enable_dynamic_strategy_router: bool = True
    router_allowed_reasons: tuple[str, ...] = ()
    router_blocked_reasons: tuple[str, ...] = ()
    router_reason_allowed_regimes: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {}
    )
    router_trend_short_factor_gate_enabled: bool = False
    router_trend_short_min_trend_strength_abs: float = 2.0
    router_trend_short_min_volume_ratio: float = 1.35
    router_trend_short_rsi_min: float = 35.0
    router_trend_short_rsi_max: float = 54.0
    router_trend_short_max_ema20_distance_atr: float = 1.8
    router_trend_short_max_ema20_distance_pct: float = 0.025
    # trend_short_factor 独立退出 profile（只在 factor gate 启用时生效）
    trend_short_factor_stop_atr: float = 2.0
    trend_short_factor_take_profit_atr: float = 1.5
    trend_short_factor_trailing_atr: float = 1.8
    trend_short_factor_max_hold_bars: int = 6
    trend_short_factor_break_even_mfe_pct: float = 0.008
    trend_short_factor_break_even_lock_pct: float = 0.002
    trend_short_factor_risk_per_trade: float = 0.035
    enable_adaptive_profiles: bool = True
    adaptive_trend_min_score: float = 3.7
    adaptive_trend_risk_per_trade: float = 0.055
    adaptive_trend_stop_atr: float = 2.4
    adaptive_trend_take_profit_atr: float = 0.55
    adaptive_trend_trailing_atr: float = 2.04
    adaptive_trend_max_hold_bars: int = 8
    adaptive_trend_allowed_regimes: tuple[str, ...] = ("downtrend",)
    enable_continuation_module: bool = False
    continuation_min_volume_ratio: float = 1.45
    continuation_min_trend_strength: float = 1.2
    continuation_risk_per_trade: float = 0.08
    continuation_stop_atr: float = 2.2
    continuation_take_profit_atr: float = 1.4
    continuation_trailing_atr: float = 1.8
    continuation_max_hold_bars: int = 16
    enable_micro_momentum_module: bool = False
    micro_momentum_min_volume_ratio: float = 1.8
    micro_momentum_min_body_atr: float = 0.7
    micro_momentum_risk_per_trade: float = 0.08
    micro_momentum_stop_atr: float = 1.4
    micro_momentum_take_profit_atr: float = 0.8
    micro_momentum_trailing_atr: float = 1.0
    micro_momentum_max_hold_bars: int = 4
    enable_funding_module: bool = False
    funding_abs_rate_threshold: float = 0.0005
    funding_min_abs_ma: float = 0.0002
    funding_risk_per_trade: float = 0.04
    funding_stop_atr: float = 2.0
    funding_take_profit_atr: float = 1.0
    funding_trailing_atr: float = 1.4
    funding_max_hold_bars: int = 12
    enable_open_interest_module: bool = False
    open_interest_min_change_pct: float = 0.08
    open_interest_min_volume_ratio: float = 1.05
    open_interest_risk_per_trade: float = 0.04
    open_interest_stop_atr: float = 1.9
    open_interest_take_profit_atr: float = 1.2
    open_interest_trailing_atr: float = 1.5
    open_interest_max_hold_bars: int = 12
    enable_trade_flow_module: bool = False
    trade_flow_min_imbalance: float = 0.45
    trade_flow_min_quote: float = 500_000.0
    trade_flow_risk_per_trade: float = 0.035
    trade_flow_stop_atr: float = 1.6
    trade_flow_take_profit_atr: float = 1.05
    trade_flow_trailing_atr: float = 1.2
    trade_flow_max_hold_bars: int = 8
    enable_attack_module: bool = False
    attack_min_score: float = 4.5
    attack_risk_per_trade: float = 0.025
    attack_max_positions: int = 2
    attack_stop_atr: float = 1.05
    attack_take_profit_atr: float = 1.0
    attack_trailing_atr: float = 1.3
    attack_max_hold_bars: int = 3
    attack_cooldown_bars: int = 48
    attack_loss_cooldown_bars: int = 384
    attack_volume_spike: float = 2.2
    attack_range_atr: float = 1.7
    attack_enabled_regimes: tuple[str, ...] = ("uptrend", "downtrend", "transition", "range")
    attack_breakout_enabled: bool = True
    attack_exhaustion_enabled: bool = True
    enable_order_book_module: bool = False
    order_book_min_depth_imbalance: float = 0.3
    order_book_min_spread_pct: float = 0.0
    order_book_max_spread_pct: float = 0.005
    order_book_risk_per_trade: float = 0.035
    order_book_stop_atr: float = 1.6
    order_book_take_profit_atr: float = 1.0
    order_book_trailing_atr: float = 1.2
    order_book_max_hold_bars: int = 8
    # --- RiskManager configuration ---
    rm_enabled: bool = True
    rm_max_single_position_pct: float = 0.80
    rm_max_total_position_pct: float = 0.80
    rm_max_daily_loss_pct: float = 15.0
    rm_max_weekly_loss_pct: float = 30.0
    rm_consecutive_loss_pause: int = 4
    rm_consecutive_loss_pause_bars: int = 96
    rm_volatility_halt_threshold: float = 0.06
    rm_max_order_book_spread_pct: float = 0.0
    rm_min_order_book_depth_quote: float = 0.0
    rm_min_liquidation_distance_pct: float = 0.015
    rm_pause_on_inconsistency: bool = True

    min_bars: int = 260
    windows_days: tuple[int, ...] = (365, 180, 90, 60, 30, 14, 7)
    validation_target_win_rate: float = 0.66
    validation_target_profit: float = 0.0
    validation_target_profit_by_window: dict[int, float] = field(
        default_factory=lambda: {
            365: 10.0,
            180: 10.0,
            90: 10.0,
            60: 10.0,
            30: 10.0,
            14: 10.0,
        }
    )
    validation_target_returns: dict[int, float] = field(
        default_factory=lambda: {
            365: 5.0,
            180: 20.0,
            90: 10.0,
            60: 2.0,
            30: 20.0,
            14: 2.0,
            7: 2.0,
        }
    )
    leverage_caps: dict[str, SymbolRisk] = field(
        default_factory=lambda: {
            "BTC-USDT-SWAP": SymbolRisk(50),
            "ETH-USDT-SWAP": SymbolRisk(50),
            "SOL-USDT-SWAP": SymbolRisk(30),
            "BNB-USDT-SWAP": SymbolRisk(30),
            "XRP-USDT-SWAP": SymbolRisk(25),
            "ADA-USDT-SWAP": SymbolRisk(25),
            "DOGE-USDT-SWAP": SymbolRisk(20),
            "LINK-USDT-SWAP": SymbolRisk(20),
            "AVAX-USDT-SWAP": SymbolRisk(20),
            "APT-USDT-SWAP": SymbolRisk(15),
            "INJ-USDT-SWAP": SymbolRisk(15),
            "SUI-USDT-SWAP": SymbolRisk(15),
            "OP-USDT-SWAP": SymbolRisk(15),
            "ARB-USDT-SWAP": SymbolRisk(15),
            "TIA-USDT-SWAP": SymbolRisk(12),
            "FIL-USDT-SWAP": SymbolRisk(12),
        }
    )
