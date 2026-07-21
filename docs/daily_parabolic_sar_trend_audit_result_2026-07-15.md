# Daily Parabolic SAR Trend Audit Result

## Frozen rule

- Rule: `daily_parabolic_sar_trend_v1`
- Universe: 28 eligible OKX perpetual symbols
- Long context: completed 4h `趋势上行`; short context: completed 4h `趋势下行`
- Signal: completed daily Parabolic SAR flip, AF step 0.02 and cap 0.20
- Entry: next daily open plus 4h delay
- Exit: opposite flip, 2 ATR(14) stop, or 10-day maximum holding period
- Cost: 0.16% round trip

## Result

| Split | Events | Net sum | Mean per event | Win rate | Positive-return month concentration |
| --- | ---: | ---: | ---: | ---: | ---: |
| Formation (2024) | 91 | -91.564546% | -1.006204% | 35.16% | 59.09% |
| OOS (2025-01-01 to 2025-07-10) | 151 | 58.306250% | 0.386134% | 44.37% | 32.13% |

Status: `historical_rejected`.

The rule is evaluated only in its intended trend contexts. Its OOS mean is positive, but its formation mean is negative and positive returns in both splits are too concentrated. This is not sufficient evidence for a reusable trend factor. The frozen SAR settings were not modified after the audit.

No standalone, paper, combination, or runner approval follows from this audit. All safety gates remain closed.
