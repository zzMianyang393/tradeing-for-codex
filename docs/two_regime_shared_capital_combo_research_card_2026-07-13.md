# Two-Regime Shared-Capital Combo Research Card

Date: 2026-07-13

Research ID: `two_regime_shared_capital_combo_v1`

Status: `pre_registered_read_only_combo_simulation`

## Components

- `donchian_long_uptrend`: frozen Donchian 20 + ATR 14 long events with completed-4h `趋势上行`
- `rsi_rebound_downtrend`: frozen RSI(14) below 35 rebound events with completed-4h `趋势下行`

The RSI component uses the full H0 downtrend bucket, not the six-event F1 subset. No component is retuned for this combination.

## Shared Capital Rules

- one shared initial account of `100,000 USDT` per split
- no component capital reservation
- maximum 5 positions across both components
- target 20% of current equity per accepted position
- no leverage and no rebalancing
- at most one active position per symbol across the entire portfolio
- entry and exit costs: 0.08% each side
- true event timestamps determine priority; exits occur before later entries
- same-time RSI candidates use lower source RSI, then symbol
- same-time Donchian candidates use symbol ascending
- daily marked-to-market equity uses completed daily closes

## Fixed Stress

Formation is repeated after removing every event signaled in 2024-11. This is a concentration test only.

## Diagnostic Gate

- OOS total return greater than zero
- OOS maximum drawdown no more than 20%
- at least 30 accepted OOS positions overall
- at least 10 accepted OOS positions from each component
- OOS top positive month contribution no more than 25%
- formation excluding 2024-11 remains profitable

Passing would permit research on a third regime component. It would not permit paper trading.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
- no execution entry integration
- no optimizer
- no parameter scan

