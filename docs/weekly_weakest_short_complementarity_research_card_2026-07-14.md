# Weekly Weakest-Short Complementarity Research Card

Date: 2026-07-14

## Frozen Question

Determine whether the post-hoc `weekly_cross_sectional_momentum_v1_short` sleeve is economically distinct from the existing drift, uptrend, downtrend-continuation, and volume-shock short weak features on one common observed window.

This audit may diagnose duplication and prospective pairing only. It cannot authorize a historical combo simulation because the weekly short sleeve was selected after the frozen long-short rule failed.

## Frozen Inputs

- window: `2025-01-01` through `2026-07-10`
- universe: the same constant 28-symbol panel used by the weekly audit
- allocation normalization: 10% per accepted position, one position per symbol
- weekly feature: short the three weakest prior-28-day performers, Monday 00:00 UTC entry, seven-day hold, 2 ATR stop, 0.16% round-trip cost
- comparison features: low-volatility drift breakout, persistent-uptrend EMA20 reclaim, EMA downtrend continuation short, and daily volume-shock reversal short
- no feature rule, cost, exit, ranking, or event timestamp may be changed

## Frozen Metrics

- active-union daily return correlation
- monthly return correlation
- active-day Jaccard overlap
- negative-day overlap coefficient
- event interval overlap, including same-symbol overlaps

## Frozen Thresholds

A pair fails the strict prospective-pair screen if either standalone has fewer than 30 accepted positions or non-positive return, daily correlation exceeds 0.35, monthly correlation exceeds 0.50, negative-day overlap exceeds 0.35, or active-day Jaccard exceeds 0.50.

Economic duplication is diagnosed separately from operational overlap. High active-day overlap alone means simultaneous risk usage, not necessarily the same alpha mechanism.

## Safety

- `weekly_cross_sectional_momentum_v1_short` remains post-hoc and non-executable.
- No pair can authorize a historical combo simulation.
- No output can enter `runner.py`.
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
