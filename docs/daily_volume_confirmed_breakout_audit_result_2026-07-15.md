# Daily Volume Confirmed Breakout Audit Result

## Frozen rule

- Rule: `daily_volume_confirmed_breakout_v1`
- Universe: 28 eligible OKX perpetual symbols
- Signal: close outside the preceding 20-day channel and quote volume at least 2.5 times the preceding five completed daily bars
- Context: long only in completed 4h `趋势上行`; short only in completed 4h `趋势下行`
- Entry: next daily open plus 4h delay
- Exit: 2 ATR(14) stop or 10-day maximum holding period
- Cost: 0.16% round trip

## Result

| Split | Events | Net sum | Mean per event | Win rate | Positive-return month concentration |
| --- | ---: | ---: | ---: | ---: | ---: |
| Formation (2024) | 77 | -84.637918% | -1.099194% | 25.97% | 80.39% |
| OOS (2025-01-01 to 2025-07-10) | 32 | -95.535933% | -2.985498% | 31.25% | 68.49% |

Status: `historical_rejected`.

The test has sufficient event counts in both splits, but the frozen volume
confirmation does not rescue the continuation hypothesis. Both net means are
negative and the small amount of positive return is highly concentrated. No
volume threshold, channel window, symbol selection, or exit condition was
changed after observing this result.

All paper, combination, and runner safety gates remain closed.
