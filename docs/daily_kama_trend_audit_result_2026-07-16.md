# Daily KAMA Trend Audit Result

Rule: `daily_kama_trend_v1`, rerun on the standard 28-symbol research universe
with its original frozen parameters. Long entries require completed `趋势上行`;
short entries require completed `趋势下行`.

| Split | Events | Mean net return | Positive-return month concentration |
| --- | ---: | ---: | ---: |
| Formation (2024) | 81 | +2.3679% | 64.36% |
| OOS (2025-01-01 to 2025-07-10) | 116 | -1.4586% | 34.39% |

The audit is `historical_rejected`. It has adequate sample counts, but OOS
average net return is negative and positive outcomes are concentrated above the
25% threshold in both windows. The regime filter correctly limits entries to
trend regimes; this result therefore rejects the frozen KAMA rule itself, not
the principle that trend and range rules should be evaluated in their respective
market regimes. It cannot enter the combo feature pool or enable paper/live
trading.
