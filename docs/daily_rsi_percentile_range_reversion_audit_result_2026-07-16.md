# Daily RSI Percentile Range Reversion Audit Result

Rule: `daily_rsi_percentile_range_reversion_v1`, rerun on the standard
28-symbol research universe with its original frozen parameters.

| Split | Events | Mean net return | Positive-return month concentration |
| --- | ---: | ---: | ---: |
| Formation (2024) | 1 | +4.1553% | 100.00% |
| OOS (2025-01-01 to 2025-07-10) | 6 | +1.3942% | 73.09% |

The audit is `insufficient_evidence`: both windows are below the 15-event
minimum. Although both small samples have positive average returns, the
positive-return month concentration also exceeds the 25% research threshold.
This is not evidence that a range sleeve is viable; it is a sparse observation,
not a directional combo feature. Paper and live-trading gates remain closed.
