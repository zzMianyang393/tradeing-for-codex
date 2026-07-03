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
    risk_per_trade: float = 0.32
    max_margin_fraction: float = 0.75
    max_total_margin_fraction: float = 0.60
    defensive_equity_fraction: float = 0.80
    defensive_risk_multiplier: float = 0.65
    defensive_margin_fraction: float = 0.35
    profit_lock_equity_fraction: float = 999.0
    profit_lock_risk_multiplier: float = 1.0
    profit_lock_margin_fraction: float = 1.0
    volatility_target_atr_pct: float = 0.022
    volatility_risk_floor: float = 0.75
    volatility_risk_power: float = 0.75
    max_trade_loss_pct_equity: float = 20.0
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
    max_positions: int = 1
    active_symbol_limit: int = 3
    short_window_symbol_limit: int = 5
    short_window_days: int = 30
    selector_lookback_bars: int = 96 * 21
    selector_momentum_weight: float = 32.0
    selector_volatility_weight: float = 140.0
    selector_trend_weight: float = 0.12
    selector_noise_penalty: float = 6.0
    stop_atr: float = 3.0
    take_profit_atr: float = 1.0
    trailing_atr: float = 2.55
    max_hold_bars: int = 8
    range_stop_atr: float = 3.0
    range_take_profit_atr: float = 1.0
    range_trailing_atr: float = 2.55
    range_max_hold_bars: int = 8
    cooldown_bars: int = 24
    loss_cooldown_bars: int = 240
    time_exit_loss_cooldown_bars: int = 96 * 3
    early_failure_bars: int = 5
    early_failure_min_mfe_pct: float = 0.002
    early_failure_max_mae_pct: float = 0.016
    early_failure_reasons: tuple[str, ...] = ("range_revert_long", "range_revert_short")
    direction_loss_pause_bars: int = 96 * 5
    direction_loss_pause_pct: float = 12.0
    short_rebound_lookback_bars: int = 96 * 3
    short_rebound_block_pct: float = 0.045
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
    long_window_days: int = 30
    long_window_preferred_symbols: tuple[str, ...] = ()
    min_score: float = 2.45
    edge_lookback_trades: int = 10
    edge_pause_bars: int = 288
    symbol_edge_lookback_trades: int = 3
    symbol_edge_min_win_rate: float = 0.50
    symbol_edge_pause_bars: int = 96 * 90
    reason_edge_lookback_trades: int = 7
    reason_edge_min_win_rate: float = 0.34
    reason_edge_pause_bars: int = 1152
    invert_signals: bool = False
    enabled_regimes: tuple[str, ...] = ("transition", "range")
    enable_adaptive_profiles: bool = True
    adaptive_trend_min_score: float = 3.7
    adaptive_trend_risk_per_trade: float = 0.055
    adaptive_trend_stop_atr: float = 2.4
    adaptive_trend_take_profit_atr: float = 0.55
    adaptive_trend_trailing_atr: float = 2.04
    adaptive_trend_max_hold_bars: int = 8
    adaptive_trend_allowed_regimes: tuple[str, ...] = ("downtrend",)
    enable_attack_module: bool = True
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
    min_bars: int = 260
    windows_days: tuple[int, ...] = (365, 180, 90, 60, 30, 14, 7)
    validation_target_win_rate: float = 0.68
    validation_target_profit: float = 0.0
    validation_target_returns: dict[int, float] = field(
        default_factory=lambda: {
            30: 100.0,
            7: 20.0,
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
