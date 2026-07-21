# Downtrend Bidirectional Combo Research Card

Date: 2026-07-13

Research ID: `downtrend_bidirectional_combo_v1`

Status: `pre_registered_read_only_combo_simulation`

## Fixed Components

- `rsi_rebound_long`: RSI(14) below 35 long rebound events in completed-4h `趋势下行`
- `ema_continuation_short`: EMA20/EMA50 bearish crossover short events in completed-4h `趋势下行`

The combination tests whether opposing weak components inside the same downtrend regime reduce exposure and drawdown. Neither component definition may be changed.

## Shared Account

- 100,000 USDT independently for formation and OOS
- maximum five positions across both components
- 20% target capital or collateral per position
- no leverage, rebalancing, or component capital reservation
- one active position per symbol across the whole account; simultaneous long and short in one symbol is prohibited
- 0.08% cost per side
- true event timestamps determine sequence; exits occur before later entries
- same-time RSI candidates use lower RSI then symbol
- same-time EMA candidates use symbol ascending
- completed daily close mark-to-market

## Stress And Gate

Formation is repeated after excluding all 2024-11 signals.

The combo cannot advance unless:

- formation, formation excluding 2024-11, and OOS returns are positive
- OOS maximum drawdown is no more than 20%
- at least 30 OOS positions are accepted
- each component contributes at least 10 accepted OOS positions
- OOS positive-month concentration is no more than 25%

The EMA short direction and RSI downtrend interpretation are both post-hoc discoveries, so a future unseen window remains mandatory even after a diagnostic pass.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
- no execution entry integration
- no optimizer or parameter scan

