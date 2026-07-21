# Daily Z-Score Range Reversion Audit Result

Rule: `daily_zscore_range_reversion_v1`, run on the standard 28-symbol
research universe with its original frozen parameters.

| Split | Events | Mean net return | Positive-return month concentration |
| --- | ---: | ---: | ---: |
| Formation (2024) | 10 | +1.5641% | 78.82% |
| OOS (2025-01-01 to 2025-07-10) | 7 | +2.4521% | 78.49% |

The audit remains `insufficient_evidence`: both windows are below 15 events.
The corrected summary now also records concentration, which exceeds the 25%
research threshold in both splits. The result is not a directional combo
feature and cannot enable paper or live trading.
