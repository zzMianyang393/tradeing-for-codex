# Regime Component Walk-Forward Audit

Date: 2026-07-13

Observed historical stability research. This is not a new unseen validation.

## Aggregate Results

| Component | Regime | Events | Accepted | Return | Max DD | Win | Positive Folds | Month Concentration | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `uptrend_donchian_55_20_long` | uptrend | 152 | 73 | +63.297601% | 37.080400% | 31.51% | 1/5 | 29.98% | `historical_walk_forward_rejected` |
| `uptrend_supertrend_4h_long` | uptrend | 172 | 146 | -6.750606% | 38.187800% | 26.03% | 2/5 | 43.02% | `historical_walk_forward_rejected` |
| `range_bb_reversion_4h` | range | 1514 | 1032 | -70.356208% | 72.370000% | 47.29% | 1/5 | 10.00% | `historical_walk_forward_rejected` |
| `range_rsi_reversion_4h` | range | 769 | 567 | -52.951929% | 55.234200% | 41.45% | 0/5 | 10.95% | `historical_walk_forward_rejected` |

## Fold Returns

| Component | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `uptrend_donchian_55_20_long` | -0.238590% | +110.063724% | -8.660075% | -4.692565% | -10.488522% |
| `uptrend_supertrend_4h_long` | -2.507969% | +19.052224% | -17.263894% | -12.615685% | +11.124758% |
| `range_bb_reversion_4h` | -6.220369% | -43.980117% | -36.043768% | +3.124083% | -16.684937% |
| `range_rsi_reversion_4h` | -3.634700% | -32.459438% | -19.616516% | -2.012526% | -12.836205% |

## Decisions

- `uptrend_donchian_55_20_long`: aggregate maximum drawdown 37.080400% > 20%; positive half-year folds 1/5 < 3/5; top positive month share 29.98% > 25%
- `uptrend_supertrend_4h_long`: aggregate return -6.750606% <= 0%; aggregate maximum drawdown 38.187800% > 20%; positive half-year folds 2/5 < 3/5; top positive month share 43.02% > 25%
- `range_bb_reversion_4h`: aggregate return -70.356208% <= 0%; aggregate maximum drawdown 72.370000% > 20%; positive half-year folds 1/5 < 3/5
- `range_rsi_reversion_4h`: aggregate return -52.951929% <= 0%; aggregate maximum drawdown 55.234200% > 20%; positive half-year folds 0/5 < 3/5

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
