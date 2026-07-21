# Downtrend Rebound Event-Time Filter Research Card

Date: 2026-07-13

Research ID: `downtrend_rebound_event_time_filter_v1`

Status: `pre_registered_read_only_audit`

Paper eligibility: `eligible_for_paper = false`

## Research Question

Inside the completed-4h `趋势下行` bucket, can information available no later than the RSI rebound entry time separate useful rebound events from weak ones?

This card follows the failed monthly Donchian/EMA diagnostics. It does not reuse same-month feature activity and does not define an executable portfolio strategy.

## Frozen Source Rule

- source: `daily_rsi_mean_revert`
- RSI period: 14
- entry threshold: completed daily RSI below 35
- exit threshold: completed daily RSI recovers to 50
- maximum hold: 10 days
- round-trip cost: 0.16%
- regime gate: existing event must have `entry_regime == 趋势下行`
- formation: 2024-01-01 through 2024-12-31
- OOS: 2025-01-01 through 2025-07-10

No source signal parameter may be changed.

## Event-Time Features

`prior_downtrend_4h_streak` counts consecutive completed-4h `趋势下行` labels whose availability timestamp is strictly earlier than entry. A label becoming available exactly at entry is excluded.

`signal_rsi` is the frozen source RSI value calculated from the completed daily candle that created the event. It is descriptive input available at the source signal time, not a value reconstructed from future bars.

## Frozen Hypotheses

| ID | Rule |
| --- | --- |
| H0 | All source RSI events already labeled `趋势下行` |
| F1 | `1 <= prior_downtrend_4h_streak <= 6` |
| F2 | `prior_downtrend_4h_streak >= 7` |
| F3 | `signal_rsi < 25` |
| F4 | `25 <= signal_rsi < 35` |

F1-F4 are parallel diagnostics. No winner will be selected by retuning these boundaries after seeing results.

## Advancement Screen

A filtered hypothesis cannot advance unless all conditions hold:

- formation and OOS net sums are positive
- OOS has at least 20 events
- OOS win rate is at least 40%
- at least 6 active months exist across formation and OOS
- top positive month contribution is at most 25% in formation and OOS
- removing 2024-11 leaves formation mean return positive
- the filter is not worse than H0 in both formation and OOS mean return

Passing this screen would only justify a future-window validation. It would not approve paper trading.

## Safety Gates

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
- no trading entry module integration
- no dynamic optimizer
- no parameter scan

