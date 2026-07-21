# Combo Auxiliary Feature Time Series

Date: 2026-07-13

## Purpose

This diagnostic extracts read-only time series for auxiliary combo features that already have full event reports.

It covers:

- `context_label`
- `risk_filter_candidate`

It excludes directional weak signals, blocked features, aggregate-only features, and document-only features.

## Output

Machine-readable output:

- `reports/combo_aux_feature_timeseries.json`

Current extraction:

- 5 features
- 650 auxiliary events
- 44 context-label events
- 606 risk-filter events

Feature event counts:

- `feat_funding_term_carry`: 20
- `feat_daily_low_turnover_momentum`: 21
- `feat_daily_ma_alignment`: 3
- `feat_daily_oi_independent_change`: 187
- `feat_range_regime_mean_reversion_family`: 419

Risk filters are normalized as veto-only events:

- `veto_flag = 1`
- `value = 1.0`

This prevents risk filters from being interpreted as directional alpha.

## Safety Gates

The report keeps:

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
