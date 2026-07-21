# Combo Research Matrix

Date: 2026-07-13

## Purpose

This diagnostic aligns directional weak-signal series with auxiliary context and risk-filter series at monthly resolution.

It is a matrix for inspection, not a combo backtest.

## Output

Machine-readable output:

- `reports/combo_research_matrix.json`

Current matrix after RSI semantic repair:

- 25 monthly rows
- first month: `2024-01`
- last month: `2026-05`
- 10 features
- 5 directional weak-signal series
- 3 context-label series
- 2 risk-filter candidate series

RSI update:

- `feat_daily_rsi_mean_revert` now contributes a monthly return series from `reports/daily_rsi_downtrend_rebound_regime_conditioned_audit.json`.
- It contributes 201 declared-compatible events: 59 formation and 142 OOS.

The matrix includes:

- directional feature monthly net-return diagnostics
- auxiliary feature monthly event counts
- auxiliary feature monthly value sums
- missing-month diagnostics per feature

## Safety Gates

The report keeps:

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
