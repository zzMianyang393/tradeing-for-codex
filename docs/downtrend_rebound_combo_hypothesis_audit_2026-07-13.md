# Downtrend Rebound Combo Hypothesis Audit

Date: 2026-07-13

Research ID: `combo_downtrend_rebound_rsi_context_v1`

## Purpose

This audit tests the frozen diagnostic hypotheses from `docs/downtrend_rebound_combo_research_card_2026-07-13.md`.

It is read-only and diagnostic:

- no runner integration
- no order generation
- no paper-trading approval
- no executable entry-time claim for H1/H2

## Output

Machine-readable output:

- `reports/downtrend_rebound_combo_hypothesis_audit.json`

## Scope

Input:

- `reports/combo_feature_timeseries.json`

Filtered regime:

- completed-4h `趋势下行`

Counts:

- source events: `631`
- downtrend-bucket events: `422`

## Hypothesis Results

### H3: RSI Standalone Bucket Baseline

This is the control group.

Formation:

- events: `59`
- net: `+446.486403%`
- mean: `+7.567566%`
- win rate: `69.49%`
- active months: `8`
- top positive month share: `44.74%`

OOS:

- events: `142`
- net: `+302.720049%`
- mean: `+2.131831%`
- win rate: `56.34%`
- active months: `7`
- top positive month share: `28.35%`

Decision:

- Alpha trace remains visible.
- The hypothesis still fails concentration discipline because formation and OOS both exceed the `25%` top-positive-month cap.

Rejection reasons:

- `formation top positive month share 44.74% > 25%`
- `OOS top positive month share 28.35% > 25%`

### H1: RSI Primary, Donchian Veto

Formation:

- events: `0`
- net: `0.000000%`

OOS:

- events: `1`
- net: `+14.740295%`
- win rate: `100.00%`
- active months: `1`

Decision:

- Rejected as a research direction.
- The Donchian veto is too destructive and leaves no usable sample.

Rejection reasons:

- `active months 1 < 6`
- `all top positive month share 100.00% > 25%`
- `OOS top positive month share 100.00% > 25%`
- `worse than H3 baseline in both formation and OOS`

### H2: RSI Primary, EMA Confirmation

Formation:

- events: `35`
- net: `+249.742598%`
- mean: `+7.135503%`
- win rate: `71.43%`
- active months: `3`
- top positive month share: `80.80%`

OOS:

- events: `108`
- net: `+18.222615%`
- mean: `+0.168728%`
- win rate: `50.00%`
- active months: `5`
- top positive month share: `39.14%`

Decision:

- Rejected as an improvement over H3.
- It lowers OOS net return from `+302.720049%` to `+18.222615%`.
- It remains too concentrated and performs worse than the baseline in both formation and OOS.

Rejection reasons:

- `all top positive month share 26.84% > 25%`
- `formation top positive month share 80.80% > 25%`
- `OOS top positive month share 39.14% > 25%`
- `worse than H3 baseline in both formation and OOS`

## Conclusion

The `趋势下行` bucket remains interesting because the RSI rebound baseline has a real positive trace across both formation and OOS.

But the first two context-combo ideas do not improve it:

- Donchian veto kills sample size.
- EMA confirmation keeps sample size but destroys most OOS return.
- RSI baseline itself still violates concentration discipline.

Therefore this card must not advance to combo backtest or paper trading.

## Next Research Direction

The next step should not be another monthly diagnostic filter.

A valid next attempt must use event-time available context, for example:

- completed prior 4h regime persistence count
- prior-day realized volatility compression/expansion
- prior completed-day RSI distance from threshold
- OI risk-filter state available at 16:15 UTC

These must be pre-registered before testing.

## Safety Gates

The report keeps:

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
