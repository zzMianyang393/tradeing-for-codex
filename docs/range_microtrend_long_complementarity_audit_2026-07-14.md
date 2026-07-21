# Range Microtrend Long Complementarity Audit

Date: 2026-07-14

Post-hoc weak-feature diagnostic. No historical combo simulation is authorized.

## Normalized Components

| Component | Accepted | Return | Max DD | Win | Month Concentration |
| --- | ---: | ---: | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | 574 | +23.313971% | 17.291600% | 38.50% | 10.13% |
| `persistent_uptrend_ema20_reclaim_v1` | 50 | +0.624101% | 2.113000% | 22.00% | 67.13% |
| `ema_continuation_short_downtrend_v1` | 67 | +10.905150% | 8.419900% | 53.73% | 35.66% |
| `daily_volume_shock_reversal_v1_short` | 75 | +9.376166% | 11.839900% | 52.00% | 19.03% |
| `weekly_range_microtrend_continuation_v1_long` | 76 | +2.034988% | 2.891700% | 64.47% | 20.09% |

## Pair Metrics

| Comparison | Daily Corr | Monthly Corr | Active Jaccard | Negative Overlap | Same-Symbol Overlaps | Diagnosis | Strict Pair |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | -0.0011 | +0.2968 | 8.03% | 70.59% | 15 | `economic_duplication_risk` | `false` |
| `persistent_uptrend_ema20_reclaim_v1` | -0.0068 | -0.1032 | 3.33% | 0.00% | 0 | `distinct_return_pattern_and_limited_operational_overlap` | `true` |
| `ema_continuation_short_downtrend_v1` | -0.0162 | +0.2165 | 7.56% | 17.65% | 0 | `distinct_return_pattern_and_limited_operational_overlap` | `true` |
| `daily_volume_shock_reversal_v1_short` | -0.0115 | -0.4709 | 3.39% | 5.88% | 0 | `distinct_return_pattern_and_limited_operational_overlap` | `true` |

## Decisions

- `weekly_range_microtrend_continuation_v1_long__low_volatility_drift_bb_breakout_fixed_risk_v1`: negative-day overlap coefficient > 0.35
- `weekly_range_microtrend_continuation_v1_long__persistent_uptrend_ema20_reclaim_v1`: retain for prospective pair comparison only
- `weekly_range_microtrend_continuation_v1_long__ema_continuation_short_downtrend_v1`: retain for prospective pair comparison only
- `weekly_range_microtrend_continuation_v1_long__daily_volume_shock_reversal_v1_short`: retain for prospective pair comparison only

## Safety

- restricted combo simulation authorized: `false`
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
