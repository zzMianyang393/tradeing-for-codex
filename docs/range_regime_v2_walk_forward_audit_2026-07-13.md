# Mean-Reverting Range V2 Walk-Forward Audit

Date: 2026-07-13

Post-hoc label refinement on observed data; prospective validation remains mandatory.

## Label Split

- `mean_reverting_range_v2`: 10942 (37.40%)
- `low_volatility_drift_v2`: 18317 (62.60%)

## Results

| Component | Events | Accepted | Return | Max DD | Win | Positive Folds | Month Concentration | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `range_bb_reversion_4h` | 108 | 105 | -7.798681% | 15.994400% | 52.38% | 1/5 | 15.69% | `posthoc_historical_rejected` |
| `range_rsi_reversion_4h` | 40 | 38 | -1.155477% | 8.486400% | 44.74% | 1/5 | 31.82% | `posthoc_historical_rejected` |

## Fold Returns

| Component | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `range_bb_reversion_4h` | -0.439318% | -4.568727% | -8.181853% | -3.483493% | +9.503610% |
| `range_rsi_reversion_4h` | +0.000000% | -0.868437% | +2.208922% | -0.458484% | -1.995143% |

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
