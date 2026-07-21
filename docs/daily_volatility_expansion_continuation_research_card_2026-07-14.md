# Daily Volatility Expansion Continuation: Research Card

Date: 2026-07-14

## Status

`prospective_cohort_b_admitted_not_yet_audited`

This is a signal-only research card. It is not an approved strategy, paper
candidate, or position rule.

## Frozen Rule

- data: OKX 15m OHLCV, resampled into completed UTC daily bars;
- volatility baseline: Wilder ATR(20), using only bars ending before the
  current day;
- trigger: daily true range is at least `1.80 * prior ATR(20)`;
- long trigger: completed daily close is in the top 25% of that day's range;
- short trigger: completed daily close is in the bottom 25% of that day's
  range;
- no signal: close location strictly between 25% and 75%, zero-range bars, or
  unavailable ATR;
- eligibility: the label known at the next daily open must normalize to
  `高波动转换`;
- signal timestamp: next UTC daily open, after the completed daily bar and all
  completed 4h labels are available;
- evaluation convention for the later sealed audit only: 4h entry delay,
  0.16% round-trip friction, and a maximum 7-day horizon.

## Historical Audit Contract

- formation: `2024-01-01` through `2024-12-31`;
- OOS: `2025-01-01` through `2025-07-10`;
- report all signals and `高波动转换`-compatible signals separately;
- require at least 15 compatible events in both formation and OOS before a
  directional-feature recommendation;
- report the contribution of `2024-11` and reject an apparent edge whose
  contribution exceeds 25% and becomes negative without that month;
- no parameter grid, threshold relaxation, or direction-specific retuning.

## Guardrails

- no time-of-day window, funding, OI, order-book, external-event, or leverage
  input;
- no retrospective signals before Cohort B starts;
- semantic overlap with `daily_volume_shock_reversal_v1_short` must be audited
  before a future combination can treat the two signals as independent votes;
- all output remains observation-only with no order, position, exit, PnL, or
  return fields.
