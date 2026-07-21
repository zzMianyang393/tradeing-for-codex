# Combo Context/Risk Feature Inventory

Date: 2026-07-13

## Purpose

This report inventories non-directional combo research features before any combo backtest is allowed.

It answers one narrow question: which `context_label` and `risk_filter_candidate` features already have enough evidence to be converted into read-only time series later?

## Rules

- Directional weak signals are excluded from this inventory.
- Risk filters are veto-only and cannot become directional signals.
- Document-only and aggregate-only features remain metadata until a schema is defined.
- No feature is approved for standalone use, paper trading, or live trading.

## Current Output

Machine-readable output:

- `reports/combo_context_risk_feature_inventory.json`

Current counts:

- `context_label`: 17
- `risk_filter_candidate`: 4
- `event_series_available`: 5
- `preview_only`: 1
- `aggregate_only`: 11
- `document_only`: 4

Ready for auxiliary series extraction:

- `feat_funding_term_carry`
- `feat_daily_low_turnover_momentum`
- `feat_daily_ma_alignment`
- `feat_daily_oi_independent_change`
- `feat_range_regime_mean_reversion_family`

Risk-filter caveat:

Two risk filters now have full event series: `daily_oi_independent_change` and `range_regime_mean_reversion_family`. `multi_coin_funding_crowding` and `range_regime_funding_extreme` remain aggregate-only, so they must not be used as hard veto rules until event-level outputs are regenerated or a veto schema is manually reviewed.

The output classifies each auxiliary feature as one of:

- `event_series_available`
- `preview_only`
- `aggregate_only`
- `document_only`
- `missing_evidence`

## Safety Gates

The generated report keeps:

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
