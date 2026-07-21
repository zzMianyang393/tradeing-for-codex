# Weak Component Complementarity Audit

Date: 2026-07-13

Observed-data meta-audit. This is not a combined portfolio backtest.

## Standalone Normalized Components

| Component | Accepted | Return | Max DD | Win | Avg Exposure | Month Concentration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | 787 | +64.447086% | 17.291600% | 40.28% | 17.00% | 7.47% |
| `persistent_uptrend_ema20_reclaim_v1` | 90 | +4.697309% | 2.113000% | 25.56% | 1.68% | 37.97% |
| `ema_continuation_short_downtrend_v1` | 67 | +10.905150% | 8.419900% | 53.73% | 4.93% | 35.66% |

## Pair Complementarity

| Pair | Daily Corr | Monthly Corr | Active Jaccard | Negative Overlap | Same-Symbol Overlaps | Eligible |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1` | +0.0602 | +0.1224 | 7.13% | 33.33% | 0 | `true` |
| `low_volatility_drift_bb_breakout_fixed_risk_v1__ema_continuation_short_downtrend_v1` | +0.2953 | +0.0722 | 19.52% | 58.82% | 19 | `false` |
| `persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1` | -0.0056 | -0.0939 | 5.06% | 7.58% | 0 | `true` |

## Decisions

- `low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1`: may proceed to a separate restricted observed-data combo simulation
- `low_volatility_drift_bb_breakout_fixed_risk_v1__ema_continuation_short_downtrend_v1`: negative-day overlap coefficient > 0.35
- `persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1`: may proceed to a separate restricted observed-data combo simulation

## Safety

- this report does not combine capital or approve a portfolio
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
