# Daily Failed Breakout Reversal: Research Card

Date: 2026-07-14

## Status

`prospective_cohort_b_admitted_not_yet_audited`

This is a signal-only research card. It does not authorize a short position or
paper trade.

## Frozen Rule

- data: OKX 15m OHLCV, resampled into completed UTC daily bars;
- channel: prior 20 completed daily highs, excluding the current daily bar;
- volatility baseline: prior Wilder ATR(20);
- trigger: the current daily high exceeds the prior 20-day channel high by at
  least `0.25 * prior ATR(20)`;
- failure confirmation: the completed daily close is below the prior channel
  high and the upper wick is at least 40% of the completed day's range;
- direction: short only;
- eligibility: the label known at the next daily open must normalize to
  `高波动转换`;
- signal timestamp: next UTC daily open, after the breakout failure and all
  completed 4h labels are available;
- evaluation convention for the later sealed audit only: 4h entry delay,
  0.16% round-trip friction, ATR stop at `1.5 * ATR(20)`, and maximum 5-day
  horizon.

## Historical Audit Contract

- formation: `2024-01-01` through `2024-12-31`;
- OOS: `2025-01-01` through `2025-07-10`;
- report all failure events and `高波动转换`-compatible events separately;
- require at least 15 compatible events in both formation and OOS before a
  directional-feature recommendation;
- report `2024-11` contribution; reject a candidate whose positive result is
  concentrated above 25% in that month and turns negative when it is removed;
- no channel-length, wick, ATR-distance, stop, or horizon sweep.

## Guardrails

- no averaging down, grid, martingale, lock, or multi-leg hedge;
- no future channel bar, post-close regime label, OI, funding, or external
  event input;
- the rule is semantically related to the existing volume-shock short, so an
  overlap audit is mandatory before a future combination counts both;
- all output remains observation-only with no order, position, exit, PnL, or
  return fields.
