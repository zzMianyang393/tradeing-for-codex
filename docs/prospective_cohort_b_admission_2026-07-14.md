# Cohort B: Second Prospective Factor Admission

Date: 2026-07-14

## Purpose

The first prospective cohort is sealed at a common data cutoff of
`2026-07-13 08:15:00` with 28 immutable observations.  This document admits a
separate, small batch of mechanism-distinct weak-factor hypotheses.  It does
not add them to the original cohort, generate a backfilled signal, or assess a
return.

## Cohort Boundary

- cohort id: `prospective_cohort_b_2026-07-14`
- no-earlier-than start: `2026-07-14 00:00:00 UTC`
- observation horizon: 90 days per emitted signal
- activation condition: the raw OHLCV coverage and a frozen signal-only
  generator must both be available after the cohort start.

Signals from before the start are permanently excluded, even if the generator
is built later.  Cohort A remains unchanged.

## Admitted Hypotheses

| Candidate | Intended sleeve | Direction | Status | Why it is here |
| --- | --- | --- | --- | --- |
| `daily_rsi_downtrend_rebound_v1` | Downtrend rebound | long | frozen rule; future evidence required | Reuses the existing RSI rule with its audited downtrend-only semantic repair. It is the only candidate with historical regime-conditioned evidence, and it must prove itself in this new window. |
| `daily_volatility_expansion_continuation_v1` | High-volatility transition | rule-determined | research card required | A daily-range expansion mechanism, deliberately low turnover and unrelated to time-of-day breakouts. |
| `daily_failed_breakout_reversal_v1` | High-volatility transition | short | research card required | A failed-breakout reversal hypothesis, structurally different from continuation entries. |

The latter two have not been historically audited. They may not emit signals
until a separate frozen rule card, historical regime audit, and signal-only
generator tests are complete. This is an admission to research, not an
admission to trading.

## Non-Negotiable Exclusions

- No grid, martingale, locking, or loss-averaging logic.
- No tick, order-book, liquidation, external-event, or stale OI input.
- No multi-leg arbitrage/carry strategy whose edge is exposed to the known
  0.32% four-leg friction floor.
- No historical backfill into Cohort A or Cohort B.
- No position sizing, order, exit, PnL, return, or paper-trading field.

## Interaction Policy

`daily_rsi_downtrend_rebound_v1` can disagree with the existing downtrend
short sleeve.  Until an explicit conflict-arbitration rule is separately
frozen, both are raw observations only and neither is an accepted position.
The two high-volatility candidates have only semantic overlap with the
existing volume-shock short; they cannot be counted as independent votes in a
future combination without an overlap audit.

## Current Safety State

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
