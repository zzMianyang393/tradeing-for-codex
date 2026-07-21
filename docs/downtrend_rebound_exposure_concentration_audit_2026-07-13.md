# Downtrend Rebound Exposure Concentration Audit

Date: 2026-07-13

Raw event-return sums count every symbol separately. This audit equal-weights all symbols entering at the same timestamp, then reports the remaining overlap.

## OOS Cohort Results

| Hypothesis | Events | Entry Cohorts | Raw Sum | Cohort Sum | Cohort Mean | Cohort Win | Max Same Entry | Max Concurrent |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `H0_downtrend_rsi_baseline` | 142 | 49 | +302.720049% | +62.463313% | +1.274761% | 51.02% | 11 | 22 |
| `F1_prior_downtrend_streak_1_to_6` | 6 | 4 | +53.971175% | +32.919950% | +8.229988% | 100.00% | 3 | 3 |
| `F2_prior_downtrend_streak_ge_7` | 136 | 49 | +248.748874% | +53.373752% | +1.089260% | 48.98% | 11 | 21 |
| `F3_signal_rsi_below_25` | 1 | 1 | +18.198531% | +18.198531% | +18.198531% | 100.00% | 1 | 1 |
| `F4_signal_rsi_25_to_35` | 141 | 49 | +284.521518% | +59.970143% | +1.223880% | 51.02% | 11 | 21 |

## Baseline Interpretation

- formation: 59 events become 22 entry cohorts; raw sum +446.486403% becomes cohort sum +123.145611%.
- OOS: 142 events become 49 entry cohorts; raw sum +302.720049% becomes cohort sum +62.463313%.
- OOS maximum simultaneous positions: 22.
- OOS maximum symbols entering together: 11.
- OOS cohort positive-month concentration: 22.73%.
- The next valid engineering step is a capital-constrained daily portfolio simulator; no raw sum above should be read as account return.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
