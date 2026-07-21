# Daily Regression-Channel Trend Audit Result

Rule: `daily_regression_channel_trend_v1`, rerun on the standard 28-symbol
research universe with its original frozen parameters. Long entries require
completed `趋势上行`; short entries require completed `趋势下行`.

| Split | Events | Mean net return | Positive-return month concentration |
| --- | ---: | ---: | ---: |
| Formation (2024) | 115 | +2.9477% | 75.29% |
| OOS (2025-01-01 to 2025-07-10) | 151 | -3.4314% | 43.49% |

The audit is `historical_rejected`. Both windows have adequate event counts,
but OOS mean net return is negative and positive outcomes are concentrated above
the 25% threshold in both splits. The rule was already constrained to its
declared trend regimes, so this rejects the frozen regression-channel signal,
not regime-aware evaluation. It cannot enter the combo feature pool or enable
paper/live trading.
