# Downtrend Rebound Capital-Constrained Simulation

Date: 2026-07-13

Fixed rules: 100,000 USDT initial capital per split, no leverage, five positions maximum, 20% target allocation per position, and 0.08% cost on each side.

## Results

| Hypothesis | Split | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Screen |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `H0_downtrend_rsi_baseline` | formation | 59 | 29 | 30 | +20.137568% | 14.422400% | 62.07% | 19.44% | 99.51% | blocked |
| `H0_downtrend_rsi_baseline` | oos | 142 | 49 | 93 | -6.160617% | 37.016300% | 53.06% | 44.71% | 100.00% | blocked |
| `F1_prior_downtrend_streak_1_to_6` | formation | 7 | 7 | 0 | +6.927996% | 6.996300% | 71.43% | 8.77% | 81.47% | blocked |
| `F1_prior_downtrend_streak_1_to_6` | oos | 6 | 6 | 0 | +11.122055% | 4.645000% | 83.33% | 6.66% | 63.63% | blocked |
| `F2_prior_downtrend_streak_ge_7` | formation | 50 | 26 | 24 | +21.955894% | 18.043800% | 65.38% | 17.08% | 99.50% | blocked |
| `F2_prior_downtrend_streak_ge_7` | oos | 136 | 49 | 87 | -4.169673% | 37.016300% | 53.06% | 44.09% | 100.00% | blocked |
| `F3_signal_rsi_below_25` | formation | 0 | 0 | 0 | +0.000000% | 0.000000% | 0.00% | 0.00% | 0.00% | blocked |
| `F3_signal_rsi_below_25` | oos | 1 | 1 | 0 | +3.633847% | 0.785100% | 100.00% | 19.53% | 22.82% | blocked |
| `F4_signal_rsi_25_to_35` | formation | 59 | 29 | 30 | +20.137568% | 14.422400% | 62.07% | 19.44% | 99.51% | blocked |
| `F4_signal_rsi_25_to_35` | oos | 141 | 49 | 92 | -9.867219% | 39.504100% | 51.02% | 44.70% | 100.00% | blocked |

## OOS Screen Details

### H0_downtrend_rsi_baseline

- total return <= 0
- maximum drawdown 37.02% > 20%

### F1_prior_downtrend_streak_1_to_6

- accepted positions 6 < 20
- positive-month concentration 60.13% > 25%

### F2_prior_downtrend_streak_ge_7

- total return <= 0
- maximum drawdown 37.02% > 20%

### F3_signal_rsi_below_25

- accepted positions 1 < 20
- positive-month concentration 100.00% > 25%

### F4_signal_rsi_25_to_35

- total return <= 0
- maximum drawdown 39.50% > 20%

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
