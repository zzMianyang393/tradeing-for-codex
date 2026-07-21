# Daily ATR Expansion Breakout Audit Result

## Frozen rule

- Rule: `daily_atr_expansion_breakout_v1`
- Universe: 28 eligible OKX perpetual symbols
- Signal: close beyond the prior 20 daily highs or lows, with daily range at least 1.5 ATR(14)
- Context: long only in completed 4h `趋势上行`; short only in completed 4h `趋势下行`
- Entry: next daily open plus 4h delay
- Exit: 2 ATR(14) stop or 10-day maximum holding period
- Cost: 0.16% round trip

## Result

| Split | Events | Net sum | Mean per event | Win rate | Positive-return month concentration |
| --- | ---: | ---: | ---: | ---: | ---: |
| Formation (2024) | 147 | 242.764494% | 1.651459% | 37.42% | 71.37% |
| OOS (2025-01-01 to 2025-07-10) | 123 | -836.059795% | -6.797234% | 21.14% | 31.20% |

Status: `historical_rejected`.

The formation result is dominated by a small number of positive months. The OOS result is strongly negative, principally through short breakout losses when the trend label lagged a sharp reversal. Of 270 total events, 128 exited through the fixed ATR stop and 142 through the time limit. The largest OOS losses were checked against their recorded entry, stop, and exit values; no post-result parameter change was made.

No standalone, paper, combination, or runner approval follows from this audit. All safety gates remain closed.
