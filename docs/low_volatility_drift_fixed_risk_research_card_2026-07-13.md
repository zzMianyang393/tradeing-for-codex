# Low-Volatility Drift Fixed-Risk Diagnostic Card

Date: 2026-07-13

## Status

Post-hoc risk diagnostic. The 10% position budget is introduced after observing
that the frozen signal passed return, stability, sample-size, and concentration
screens but exceeded the 20% drawdown limit. It cannot validate the component.

## Frozen Change

- keep every signal, regime, entry, exit, stop, cost, universe, and priority rule
  unchanged
- reduce allocation per accepted position from 20% to 10%
- keep maximum concurrent positions at five
- resulting nominal gross allocation cap: 50%
- unused capital remains cash

The 10% budget is a single conservative half-risk diagnostic. No allocation grid
is permitted.

## Screen

Retain the original historical screen: at least 30 accepted positions, positive
aggregate return, drawdown at most 20%, at least 3/5 positive half-year buckets,
and top positive month share at most 25%.

Passing creates only a frozen prospective candidate. Data through `2026-07-10`
remain observed and cannot validate the overlay.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

