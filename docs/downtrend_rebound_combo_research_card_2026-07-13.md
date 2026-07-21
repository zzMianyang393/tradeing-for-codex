# Downtrend Rebound Combo Research Card

Date: 2026-07-13

Research ID: `combo_downtrend_rebound_rsi_context_v1`

Chinese name: `趋势下行超卖反弹组合研究`

Status: `pending_research_card`

Paper eligibility: `eligible_for_paper = false`

## Purpose

This card pre-registers the next research direction identified by `reports/regime_bucket_combo_coverage.json`.

The research question is narrow:

> In completed-4h `趋势下行` regimes, can RSI downtrend rebound remain useful when Donchian and 4h EMA trend signals are used as context or veto features?

This is not a generic multi-strategy blend. It is a regime-bucket study.

## Registered Regime Bucket

- regime label: completed-4h `趋势下行`
- label source: `regime_validation.py`
- label availability: after completed 4h candle close only
- allowed feature extraction: events whose `entry_regime == 趋势下行`

## Candidate Features

| Feature ID | Source Research ID | Role In This Card | Evidence | Notes |
| --- | --- | --- | --- | --- |
| `feat_daily_rsi_mean_revert` | `daily_rsi_mean_revert` | primary directional rebound signal | 15 active months, net `+749.206452%` inside `趋势下行` | Post-hoc semantic repair; requires future-window validation. |
| `feat_4h_ema_crossover` | `4h_ema_crossover` | context/veto comparator | 8 active months, net `+83.197129%` inside `趋势下行` | May identify tradable downside trend structure. |
| `feat_donchian_atr_trend_baseline` | `donchian_atr_trend_baseline` | opposing-state context or veto, not automatic vote | 15 active months, net `-244.245997%` inside `趋势下行` | Negative sum warns against naive voting. |

Pair overlap from the coverage review:

| Pair | Common Active Months |
| --- | ---: |
| `feat_daily_rsi_mean_revert` + `feat_donchian_atr_trend_baseline` | 14 |
| `feat_4h_ema_crossover` + `feat_daily_rsi_mean_revert` | 8 |
| `feat_4h_ema_crossover` + `feat_donchian_atr_trend_baseline` | 7 |

## Frozen Combo Hypotheses

Only the following hypotheses may be tested later. No parameter edits are allowed inside this card.

### H1: RSI Primary, Donchian Veto

- Start from existing `feat_daily_rsi_mean_revert` events.
- Keep only events in completed-4h `趋势下行`.
- Reject an RSI event if Donchian has an active same-month `趋势下行` signal with negative monthly net-return diagnostic in the formation window.
- Do not change RSI(14), threshold 35, recovery 50, or max 10-day hold.

### H2: RSI Primary, EMA Confirmation

- Start from existing `feat_daily_rsi_mean_revert` events.
- Keep only events in completed-4h `趋势下行`.
- Allow an RSI event only when `feat_4h_ema_crossover` has at least one same-month compatible `趋势下行` event in the diagnostic matrix.
- Do not alter EMA parameters or RSI parameters.

### H3: RSI Standalone Bucket Baseline

- Start from existing `feat_daily_rsi_mean_revert` events.
- Keep only events in completed-4h `趋势下行`.
- No Donchian or EMA filter.
- This exists only as the control group for H1 and H2.

## Required Split

The initial diagnostic window remains:

- formation: `2024-01-01` to `2024-12-31`
- OOS: `2025-01-01` to `2025-07-10`

Because the `趋势下行` semantic repair was discovered after inspection, a future-window validation must be required before any paper-trading discussion. This card cannot be promoted using only the current OOS window.

## Cost And Turnover

Required assumptions:

- one-leg directional round trip cost floor: `0.16%`
- no multi-leg hedge execution
- no portfolio leverage multiplier
- no martingale, grid, averaging down, or lock order logic
- monthly turnover must remain compatible with average hold time `>= 3` days

## Rejection Rules

Reject the combo research if any condition occurs:

- H1 or H2 performs worse than H3 in both formation and OOS.
- Any top positive month contributes more than `25%` of total positive return after filters.
- Removing `2024-11` turns formation expectancy negative.
- OOS net sum is negative.
- OOS win rate is below `40%`.
- Common active months after filtering fall below `6`.
- Any implementation imports or calls `runner.py`.

## Safety Gates

This card explicitly keeps:

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

Allowed next step:

- implement a read-only hypothesis audit script that consumes existing feature events

Current diagnostic result:

- `reports/downtrend_rebound_combo_hypothesis_audit.json`
- `docs/downtrend_rebound_combo_hypothesis_audit_2026-07-13.md`
- H1 Donchian veto: rejected because sample collapses to 1 OOS event.
- H2 EMA confirmation: rejected because it performs worse than H3 in both formation and OOS.
- H3 RSI baseline: still positive, but rejected for concentration discipline.

Disallowed next steps:

- no paper trading
- no runner integration
- no live order path
- no dynamic weight optimizer
- no OOS-driven retuning
