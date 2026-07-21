# Weak Component Complementarity Research Card

Date: 2026-07-13

Status: frozen observed-data meta-audit; not a portfolio backtest.

## Components

- `low_volatility_drift_bb_breakout_fixed_risk_v1`: frozen prospective candidate, all data-eligible symbols
- `persistent_uptrend_ema20_reclaim_v1`: BTC/ETH weak-feature watchlist item with concentration penalty
- `ema_continuation_short_downtrend_v1`: downtrend short watchlist item with concentration penalty

No underlying entry, exit, regime, cost, or holding rule may be changed in this audit.

## Window And Capital Normalization

- observed data only: 2024-01-01 through 2026-07-10
- no signal or return after 2026-07-10 may be read
- each component is reconstructed independently with 100,000 USDT
- 10% equity per position, maximum five positions, one position per symbol
- the existing 0.16% round-trip event cost remains embedded

## Fixed Metrics

For each component:

- accepted positions, return, maximum drawdown, win rate, exposure, monthly concentration
- daily marked-to-market return series on one common calendar

For each pair:

- Pearson correlation of daily returns on the union of both components' active days
- Pearson correlation of compounded monthly returns
- active-day Jaccard overlap
- negative-day overlap coefficient: joint negative days divided by the smaller negative-day count
- accepted-event interval overlap, including same-symbol overlap

## Restricted Combination Eligibility

A pair may proceed only to a separate observed-data combination simulation when all are true:

- each component has at least 30 accepted positions
- each component has positive standalone observed return after cost
- active-union daily return correlation is no greater than 0.35
- monthly return correlation is no greater than 0.50
- negative-day overlap coefficient is no greater than 0.35
- active-day Jaccard overlap is no greater than 0.50

Passing this meta-audit only authorizes a restricted research simulation. It does not permit paper trading, prospective-result inspection, or production integration.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
