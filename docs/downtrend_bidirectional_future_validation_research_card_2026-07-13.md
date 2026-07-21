# Downtrend Bidirectional Future Validation Research Card

Date: 2026-07-13

## Purpose

Validate the post-hoc fixed-risk-budget combination on a previously untouched
window. This is a locked validation, not a new optimization round.

## Untouched Window

- Start: `2025-07-11 00:00:00 UTC`
- End: `2026-07-10 23:45:00 UTC`
- Data: official OKX 15-minute OHLCV archives already present locally
- Universe: the 28 symbols passing
  `reports/future_window_data_coverage_audit.json`
- Exclusion: `SEI-USDT-SWAP`, solely because target-window coverage is below the
  pre-outcome data threshold

The eligible universe is frozen from the coverage audit before strategy returns
are calculated. Symbols cannot be added or removed based on performance.

## Frozen Components

### RSI rebound long

- Source rule: daily RSI(14) below 35
- Entry: next daily open after the completed signal
- Exit: RSI recovery to 50 or 10-day time exit
- Cost: 0.16% round trip
- Regime gate: entry is allowed only when the last completed 4-hour regime label
  is `downtrend`
- Component cap: at most 2 concurrent positions

### EMA continuation short

- Source rule: completed 4-hour EMA(20) crossing below EMA(50)
- Entry: next 15-minute open after the completed signal
- Exit: opposite completed cross or 5-day time exit
- Cost: 0.16% round trip
- Direction and regime gate: short events only, and entry is allowed only when
  the last completed 4-hour regime label is `downtrend`
- Component cap: at most 3 concurrent positions

## Portfolio Rules

- Initial equity: 100,000 USDT
- Maximum positions: 5
- Position allocation: 20% of equity per accepted position
- One position per symbol
- Event priority: frozen event score, then symbol
- Unused component capacity remains cash
- No leverage, parameter changes, dynamic routing, or post-result symbol filtering
- Events exiting after the frozen window end are omitted

## Pre-Registered Pass Criteria

All conditions must pass:

1. Net portfolio return is greater than 0%.
2. Maximum drawdown is at most 20%.
3. At least 30 positions are accepted by the capital simulator.
4. Each component has at least 10 accepted positions.
5. Each component has positive realized return contribution.
6. The largest single-month share of positive return is at most 25%.
7. Every traded symbol passed the frozen data-coverage gate.

Failure is reported as evidence against this exact combination. No parameter or
regime-label adjustment is allowed after viewing the result; a changed design
requires a new future window.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

