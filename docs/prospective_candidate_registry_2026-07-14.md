# Prospective Candidate Registry

Date: 2026-07-14

Prospective data start: `2026-07-11`.

## Frozen Candidates

### `low_volatility_drift_bb_breakout_fixed_risk_v1`

- regime: `low_volatility_drift_v2`
- historical observed result: +64.447086% return, 17.291600% max DD
- accepted positions: 787
- positive half-year folds: 4/5
- allocation: 10% per position, maximum 5
- no result peeking before the 90-day interim checkpoint

## Watchlist

- `ema_continuation_short_downtrend_v1`: +10.256000% contribution, 43.16% positive-month concentration; not frozen for combo use.
- `persistent_uptrend_ema20_reclaim_v1`: +4.697309% observed return, 37.97% positive-month concentration; not frozen for combo use.
- `combo::low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1`: +68.241452% observed return, 17.378600% max DD, +0.087000pp DD excess; not frozen for combo use.
- `combo::persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1`: +16.121283% observed return, 8.951700% max DD, +0.531800pp DD excess; not frozen for combo use.
- `daily_volume_shock_reversal_v1_short`: +9.376166% observed return, 11.839900% max DD; not frozen for combo use.
- `pair_watchlist::daily_volume_shock_reversal_v1_short__ema_continuation_short_downtrend_v1`: complementarity gate passed; historical combo simulation prohibited; not frozen for combo use.
- `pair_watchlist::daily_volume_shock_reversal_v1_short__persistent_uptrend_ema20_reclaim_v1`: complementarity gate passed; historical combo simulation prohibited; not frozen for combo use.
- `weekly_cross_sectional_momentum_v1_short`: +76.810624% observed return, 14.434100% max DD; not frozen for combo use.
- `pair_watchlist::weekly_cross_sectional_momentum_v1_short__persistent_uptrend_ema20_reclaim_v1`: complementarity gate passed; historical combo simulation prohibited; not frozen for combo use.
- `weekly_range_microtrend_continuation_v1_long`: +2.034988% observed return, 2.891700% max DD; not frozen for combo use.
- `pair_watchlist::weekly_range_microtrend_continuation_v1_long__daily_volume_shock_reversal_v1_short`: complementarity gate passed; historical combo simulation prohibited; not frozen for combo use.
- `pair_watchlist::weekly_range_microtrend_continuation_v1_long__ema_continuation_short_downtrend_v1`: complementarity gate passed; historical combo simulation prohibited; not frozen for combo use.
- `pair_watchlist::weekly_range_microtrend_continuation_v1_long__persistent_uptrend_ema20_reclaim_v1`: complementarity gate passed; historical combo simulation prohibited; not frozen for combo use.
- `donchian_atr_trend_baseline`: 1 unique regime-compatible prospective signal; standalone status remains rejected; not frozen for combo use.

## Regime Coverage

- `uptrend`: `watchlist_only`
- `downtrend`: `watchlist_only`
- `mean_reverting_range_v2`: `watchlist_only`
- `low_volatility_drift_v2`: `one_frozen_candidate`
- `combo_layer`: `2_strict_gate_failed_watchlist`
- `volume_shock_exhaustion`: `watchlist_only`
- `cross_sectional_weakness_continuation`: `watchlist_only`
- `regime_gated_trend_breakout`: `watchlist_only`
- `prospective_pair_comparison_layer`: `6_watchlist`

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
