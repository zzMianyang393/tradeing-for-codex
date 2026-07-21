# Downtrend Bidirectional Fixed Risk Budget Research Card

Date: 2026-07-13

Research ID: `downtrend_bidirectional_fixed_risk_budget_v1`

Status: `posthoc_risk_design_diagnostic`

## Evidence For This Overlay

The frozen five-position combo lost 36.57% from 2025-01-30 to 2025-03-10. During that episode average long exposure was 86.01%, average short exposure was 0.47%, and the portfolio was net long on 39 of 40 observed days.

## Frozen Risk Budget

- RSI rebound long: maximum 2 concurrent positions, approximately 40% target gross exposure
- EMA continuation short: maximum 3 concurrent positions, approximately 60% target gross exposure
- total maximum remains 5 positions
- unused component slots remain cash and cannot be borrowed by the other component
- one active position per symbol
- each accepted position still targets 20% of current equity
- no leverage, rebalancing, dynamic hedge ratio, volatility targeting, or parameter grid
- signal rules, timestamps, exits, costs, and same-time priorities remain unchanged

## Diagnostic Gate

- formation, formation excluding 2024-11, and OOS returns remain positive
- OOS maximum drawdown falls to no more than 20%
- at least 30 OOS positions are accepted overall
- each component contributes at least 10 accepted OOS positions
- OOS positive-month concentration is no more than 25%

This 2-long / 3-short rule was designed after observing the current OOS drawdown. A pass cannot validate it; only a future unseen window can do that.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
- no execution entry integration
- no parameter scan or optimizer

