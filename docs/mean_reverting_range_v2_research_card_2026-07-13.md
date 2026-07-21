# Mean-Reverting Range V2 Research Card

Date: 2026-07-13

## Motivation

The original `range` label is a residual class: not a strong ordered EMA trend
and not high volatility. The observed structure audit shows that BB and RSI
extremes inside that class continue rather than revert. The old label and all old
reports remain unchanged.

This post-hoc research introduces a new descriptive label. It cannot claim an
unseen validation on data through `2026-07-10`.

## Frozen V2 Labels

Start from the existing completed-4h labels. Preserve existing `uptrend`,
`downtrend`, and `high-volatility transition` labels. Split only the old residual
range class using the 24-hour Kaufman efficiency ratio:

`ER(6) = abs(close[t] - close[t-6]) / sum(abs(close[i] - close[i-1]))`

- `mean_reverting_range_v2`: old range label and `ER(6) <= 0.30`
- `low_volatility_drift_v2`: old range label and `ER(6) > 0.30`

The threshold `0.30` is frozen from the conventional low-efficiency
interpretation. No threshold grid is permitted.

## Strategy Rechecks

Re-run the already frozen 4-hour BB(20, 2 standard deviations) and RSI(14,
30/70) reversion components only inside `mean_reverting_range_v2`. Entry, exit,
2-ATR stop, three-day hold, 0.16% cost, capital limits, universe, and half-year
buckets remain unchanged.

## Candidate Screen

Use the same screen as the previous component batch:

- at least 30 accepted positions
- aggregate return greater than 0%
- maximum drawdown at most 20%
- at least 3/5 positive half-year buckets
- top positive month share at most 25%

## Safety

- post-hoc label refinement; prospective validation remains mandatory
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

