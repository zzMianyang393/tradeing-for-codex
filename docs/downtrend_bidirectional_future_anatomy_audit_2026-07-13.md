# Downtrend Bidirectional Future Anatomy

Date: 2026-07-13

## Maximum Drawdown

- peak: 2025-10-11, equity 139964.052886
- trough: 2026-06-10, equity 97809.669253
- drawdown: 30.118007% over 242 days
- average long / short exposure: 24.60% / 11.42%
- net-long / neutral / net-short days: 136 / 66 / 41

## Monthly Realized PnL

| Month | ema_continuation_short | rsi_rebound_long | Total |
| --- | ---: | ---: | ---: |
| 2025-08 | +0.000000 | +4200.415124 | +4200.415124 |
| 2025-09 | +950.656435 | +1577.899540 | +2528.555975 |
| 2025-10 | +16125.963074 | +8009.057395 | +24135.020469 |
| 2025-11 | +3667.885227 | -5898.166155 | -2230.280928 |
| 2025-12 | -2200.166841 | -10029.494464 | -12229.661305 |
| 2026-01 | -1584.466360 | +3464.488981 | +1880.022621 |
| 2026-02 | -1894.157713 | -8064.058350 | -9958.216063 |
| 2026-03 | +1301.751722 | -1799.704248 | -497.952526 |
| 2026-04 | -3479.460996 | +6660.603409 | +3181.142413 |
| 2026-05 | +171.542295 | -1060.861419 | -889.319124 |
| 2026-06 | -926.325575 | -8367.724170 | -9294.049745 |
| 2026-07 | -1877.221283 | +1091.501124 | -785.720159 |

## Concentration

- `ema_continuation_short` top positive month share: 43.16%
- `rsi_rebound_long` top positive month share: 20.28%
- opposite-sign component months: 2025-11, 2026-01, 2026-03, 2026-04, 2026-05, 2026-07

## Safety

- no replacement rule or parameter was tested
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
