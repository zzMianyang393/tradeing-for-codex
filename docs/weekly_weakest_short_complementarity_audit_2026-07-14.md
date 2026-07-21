# Weekly Weakest-Short Complementarity Audit

Date: 2026-07-14

Post-hoc weak-feature diagnostic. No historical combo simulation is authorized.

## Normalized Components

| Component | Accepted | Return | Max DD | Win | Month Concentration |
| --- | ---: | ---: | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | 574 | +23.313971% | 17.291600% | 38.50% | 10.13% |
| `persistent_uptrend_ema20_reclaim_v1` | 50 | +0.624101% | 2.113000% | 22.00% | 67.13% |
| `ema_continuation_short_downtrend_v1` | 67 | +10.905150% | 8.419900% | 53.73% | 35.66% |
| `daily_volume_shock_reversal_v1_short` | 75 | +9.376166% | 11.839900% | 52.00% | 19.03% |
| `weekly_cross_sectional_momentum_v1_short` | 234 | +76.810624% | 14.434100% | 54.70% | 11.11% |

## Pair Metrics

| Comparison | Daily Corr | Monthly Corr | Active Jaccard | Negative Overlap | Same-Symbol Overlaps | Diagnosis | Strict Pair |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | +0.1208 | -0.0008 | 76.46% | 48.77% | 50 | `economic_duplication_risk` | `false` |
| `persistent_uptrend_ema20_reclaim_v1` | -0.1347 | -0.2974 | 8.27% | 32.35% | 6 | `distinct_return_pattern_and_limited_operational_overlap` | `true` |
| `ema_continuation_short_downtrend_v1` | +0.5109 | +0.7009 | 27.77% | 67.06% | 16 | `economic_duplication_risk` | `false` |
| `daily_volume_shock_reversal_v1_short` | +0.2468 | +0.2732 | 25.51% | 46.15% | 3 | `economic_duplication_risk` | `false` |

## Decisions

- `weekly_cross_sectional_momentum_v1_short__low_volatility_drift_bb_breakout_fixed_risk_v1`: negative-day overlap coefficient > 0.35; active-day Jaccard overlap > 0.50
- `weekly_cross_sectional_momentum_v1_short__persistent_uptrend_ema20_reclaim_v1`: retain for prospective pair comparison only
- `weekly_cross_sectional_momentum_v1_short__ema_continuation_short_downtrend_v1`: active-union daily return correlation > 0.35; monthly return correlation > 0.50; negative-day overlap coefficient > 0.35
- `weekly_cross_sectional_momentum_v1_short__daily_volume_shock_reversal_v1_short`: negative-day overlap coefficient > 0.35

## Safety

- restricted combo simulation authorized: `false`
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
