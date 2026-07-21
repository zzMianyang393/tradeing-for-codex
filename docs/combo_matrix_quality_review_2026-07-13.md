# Combo Matrix Quality Review

Date: 2026-07-13

## Purpose

This review checks whether the monthly combo research matrix has enough coverage for a later hypothesis test.

It is not a combo backtest.

## Output

Machine-readable output:

- `reports/combo_matrix_quality_review.json`

Current result after RSI semantic repair:

- `ready_for_combo_hypothesis_test = false`
- allowed next step: `improve_feature_coverage_or_add_directional_features`
- matrix months: 25
- directional weak signals with monthly series: 5
- context labels: 3
- risk-filter candidates: 2

Blocking reasons after regime-compatible filtering:

- directional common active months `3 < 12`
- `feat_4h_ema_crossover` zero-month share `44.00% > 40%`
- `feat_daily_bb_mean_revert` zero-month share `80.00% > 40%`
- `feat_daily_trend_pullback` zero-month share `60.00% > 40%`
- `feat_daily_ma_alignment` context zero-month share `88.00% > 80%`
- directional plus risk-filter common active months `3 < 12`

Useful detail:

- Feature-pool preflight has 5 directional candidates.
- `feat_daily_rsi_mean_revert` now uses the downtrend rebound semantic repair and contributes 201 events.
- RSI repair improves directional event count from 430 to 631 and gives the matrix 5 directional series.
- `feat_daily_trend_pullback` adds 21 declared-compatible events, but OOS compatible net remains negative.
- The matrix still fails because active-month overlap did not improve.
- A separate regime-bucket coverage review now identifies `趋势下行` and `趋势上行` as future combo research-card candidates.
- `震荡` remains coverage-insufficient because only `feat_daily_bb_mean_revert` appears there.

Related output:

- `reports/regime_bucket_combo_coverage.json`
- `docs/regime_bucket_combo_coverage_2026-07-13.md`

The gate checks:

- directional feature count
- directional common active months
- directional plus risk-filter common active months
- zero-month share by feature
- sparse context and risk-filter coverage

## Safety Gates

The report keeps:

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
