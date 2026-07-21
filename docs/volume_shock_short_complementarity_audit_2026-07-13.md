# Volume-Shock Short Complementarity Audit

Date: 2026-07-13

Common-window post-hoc weak-feature audit. No combo simulation is authorized.

## Normalized Components

| Component | Accepted | Return | Max DD | Win | Month Concentration |
| --- | ---: | ---: | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | 574 | +23.313971% | 17.291600% | 38.50% | 10.13% |
| `persistent_uptrend_ema20_reclaim_v1` | 50 | +0.624101% | 2.113000% | 22.00% | 67.13% |
| `ema_continuation_short_downtrend_v1` | 67 | +10.905150% | 8.419900% | 53.73% | 35.66% |
| `daily_volume_shock_reversal_v1_short` | 75 | +9.376166% | 11.839900% | 52.00% | 19.03% |

## Pair Metrics

| Pair | Daily Corr | Monthly Corr | Active Jaccard | Negative Overlap | Same-Symbol Overlaps | Retained |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `daily_volume_shock_reversal_v1_short__low_volatility_drift_bb_breakout_fixed_risk_v1` | -0.1164 | -0.3467 | 23.47% | 35.90% | 11 | `false` |
| `daily_volume_shock_reversal_v1_short__persistent_uptrend_ema20_reclaim_v1` | -0.1401 | -0.1197 | 8.99% | 11.76% | 0 | `true` |
| `daily_volume_shock_reversal_v1_short__ema_continuation_short_downtrend_v1` | +0.0146 | +0.0454 | 8.76% | 12.82% | 0 | `true` |

## Decisions

- `daily_volume_shock_reversal_v1_short__low_volatility_drift_bb_breakout_fixed_risk_v1`: negative-day overlap coefficient > 0.35
- `daily_volume_shock_reversal_v1_short__persistent_uptrend_ema20_reclaim_v1`: retain for prospective pair comparison only
- `daily_volume_shock_reversal_v1_short__ema_continuation_short_downtrend_v1`: retain for prospective pair comparison only

## Safety

- restricted combo simulation authorized: `false`
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
