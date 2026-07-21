# Restricted Weak-Pair Combo Research Card

Date: 2026-07-13

Status: frozen observed-data shared-capital diagnostic.

## Eligible Pairs

Only pairs that passed `weak_component_complementarity_audit` may be simulated:

- low-volatility drift breakout plus persistent-uptrend EMA20 reclaim
- persistent-uptrend EMA20 reclaim plus downtrend EMA short continuation

The drift plus downtrend-short pair is excluded because its negative-day overlap coefficient exceeded 35%.

## Frozen Portfolio Rules

- observed data only: 2024-01-01 through 2026-07-10
- one shared 100,000 USDT account
- 10% equity per accepted position
- maximum five concurrent positions across both components
- one concurrent position per symbol
- no component-specific reservation or optimized weight
- same-timestamp priority: frozen event score, then symbol
- existing event costs remain embedded
- no leverage, rebalance, pyramiding, grid, or martingale

## Fixed Folds

- 2024-H1
- 2024-H2
- 2025-H1
- 2025-H2
- 2026-H1 through 2026-07-10

## Diagnostic Gate

A pair passes the observed shared-capital diagnostic only when all are true:

- at least 50 accepted positions
- positive aggregate return after cost
- maximum drawdown no greater than the worse standalone component drawdown
- at least 3 of 5 positive folds
- top positive-month contribution no greater than 25%
- each component contributes positive realized PnL
- each component has at least 10 accepted positions

A passing result remains post-hoc. It may be frozen for prospective joint observation, but cannot be approved for paper trading or production.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
