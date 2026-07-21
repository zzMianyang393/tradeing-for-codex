# Downtrend Bidirectional Drawdown Anatomy

Date: 2026-07-13

## Maximum Drawdown Episode

- peak: 2025-01-30, equity 118873.348564
- trough: 2025-03-10, equity 75406.501364
- drawdown: 36.565679%
- duration: 39 days

## Exposure During Episode

- average long exposure: 86.01%
- average short exposure: 0.47%
- average net directional exposure: 85.54%
- net-long / neutral / net-short days: 39 / 1 / 0
- trough long exposure: 98.81%
- trough short exposure: 0.00%
- trough net exposure: 98.81%

## Realized PnL During Episode

| Component | Realized PnL |
| --- | ---: |
| `ema_continuation_short` | -1466.419142 |
| `rsi_rebound_long` | -22956.524158 |

## Worst Daily Equity Changes

| Date | Change | Long Exposure | Short Exposure | Net Exposure |
| --- | ---: | ---: | ---: | ---: |
| 2025-02-02 | -14.266081% | 98.99% | 0.00% | 98.99% |
| 2025-02-24 | -12.843062% | 100.00% | 0.00% | 100.00% |
| 2025-03-09 | -11.585016% | 98.88% | 0.00% | 98.88% |
| 2025-02-01 | -8.233996% | 99.14% | 0.00% | 99.14% |
| 2025-02-04 | -7.353861% | 98.96% | 0.00% | 98.96% |

## Safety

- diagnostic only; no risk overlay is tested here
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
