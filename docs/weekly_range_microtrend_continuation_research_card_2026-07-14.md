# Weekly Range Microtrend Continuation Research Card

Date: 2026-07-14

## Motivation

The return-free cross-sectional reversal preflight found only 12 Mondays with six simultaneous `mean_reverting_range_v2` symbols, so that market-neutral design stopped before outcome inspection. The same preflight found 191 symbol-level range observations across 44 Mondays.

Earlier descriptive structure evidence showed short path continuation inside the residual range class while frozen BB and RSI reversion rules lost money. This card therefore tests a different mechanism: short-lived directional continuation inside each symbol's low-efficiency range label.

## Frozen Rule

- observed window: `2025-01-01` through `2026-07-10`
- universe: constant 28-symbol panel
- schedule: Monday 00:00 UTC only
- eligibility: the symbol's latest completed 4h label is `mean_reverting_range_v2`
- direction: sign of the completed prior-24-hour close-to-close return
- portfolio priority: descending absolute prior-24-hour return, symbol as deterministic tie-break
- maximum five concurrent positions, one per symbol
- position fraction: 10% of shared equity
- stop: 2 ATR, using completed daily ATR(14)
- exit: first completed 4h label outside `mean_reverting_range_v2`, or three days, whichever occurs first
- round-trip cost: 0.16%
- no magnitude threshold and no parameter grid

## Frozen Screen

- at least 100 accepted positions
- aggregate net return greater than 0%
- maximum drawdown at most 20%
- at least 2/3 positive half-year folds
- top positive month share at most 25%
- each directional sleeve has at least 30 accepted positions and positive contribution

## Interpretation

Passing would create a frozen prospective research candidate, not a paper or live strategy. Failing cannot be repaired by changing the 24-hour lookback, schedule, hold, stop, label threshold, or symbol subset.

## Safety

- observations end at `2026-07-10`
- no prospective outcomes are read
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
