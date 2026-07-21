# Downtrend Rebound Capital Simulation Research Card

Date: 2026-07-13

Research ID: `downtrend_rebound_capital_constrained_v1`

Status: `pre_registered_read_only_portfolio_simulation`

## Purpose

Convert the frozen downtrend RSI rebound event set into a capital-constrained daily marked-to-market equity diagnostic. Raw event sums and same-entry cohort sums are not account returns.

## Frozen Portfolio Rules

- initial capital: `100,000 USDT`
- direction: long only
- leverage: none
- maximum concurrent positions: `5`
- target cash allocation per accepted position: `20%` of equity measured at that entry open
- entry cost: `0.08%`
- exit cost: `0.08%`
- no rebalancing after entry
- exits at the frozen event exit open before new entries at the same timestamp
- daily mark-to-market uses completed daily close
- formation and OOS simulations start independently from `100,000 USDT`

If same-entry candidates exceed free slots, rank by lower source `signal_rsi`, then symbol ascending. This ordering is deterministic and frozen before results.

## Registered Event Sets

- H0: all RSI rebound events inside completed-4h `趋势下行`
- F1: prior downtrend streak 1 to 6 completed 4h bars
- F2: prior downtrend streak at least 7 completed 4h bars
- F3: source signal RSI below 25
- F4: source signal RSI from 25 to below 35

No signal threshold, holding rule, regime label, or portfolio parameter may be changed in this audit.

## Required Outputs

- accepted and capacity-rejected events
- final equity and total return
- maximum daily marked-to-market drawdown
- realized trade win rate
- maximum concurrent positions
- average and peak gross exposure
- capital turnover
- daily equity series

## Interpretation Gate

This simulation remains diagnostic. No hypothesis can advance unless OOS total return is positive, OOS maximum drawdown is no more than 20%, at least 20 OOS positions are accepted, and the OOS result is not dependent on one positive month contributing more than 25%.

The post-hoc RSI downtrend semantic repair still requires a genuinely future validation window even if the current simulation passes these diagnostics.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
- no execution entry integration
- no optimizer
- no parameter scan

