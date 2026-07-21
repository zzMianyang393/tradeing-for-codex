# Downtrend Bidirectional Shared-Capital Combo

Date: 2026-07-13

RSI rebound longs and EMA continuation shorts share one account inside completed-4h downtrend regimes.

## Portfolio Results

| Window | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Month Concentration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `formation` | 69 | 38 | 31 | +15.370189% | 14.422400% | 55.26% | 20.79% | 99.51% | 39.11% |
| `formation_excluding_2024_11` | 57 | 33 | 24 | +1.677157% | 14.422400% | 48.48% | 18.81% | 99.51% | 40.46% |
| `oos` | 166 | 60 | 106 | +6.737188% | 36.565700% | 58.33% | 48.02% | 100.00% | 22.29% |

## OOS Component Attribution

| Component | Accepted | Rejected | PnL | Return Contribution | Win |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ema_continuation_short` | 14 | 10 | +3065.523801 | +3.065524% | 64.29% |
| `rsi_rebound_long` | 46 | 96 | +3671.664438 | +3.671664% | 56.52% |

## Decision

- OOS maximum drawdown 36.57% > 20%

Diagnostic status: `blocked`.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
