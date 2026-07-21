# EMA Short Downtrend Capital-Constrained Simulation

Date: 2026-07-13

Only frozen EMA20/EMA50 short events with completed-4h `趋势下行` labels are included.

## Results

| Window | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Month Concentration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `formation` | 10 | 10 | 0 | -4.713097% | 6.197400% | 40.00% | 8.59% | 60.16% | 74.50% |
| `formation_excluding_2024_11` | 10 | 10 | 0 | -4.713097% | 6.197400% | 40.00% | 8.59% | 60.16% | 74.50% |
| `oos` | 24 | 15 | 9 | +6.097386% | 4.145500% | 66.67% | 6.78% | 99.98% | 35.55% |

## Decision

- formation total return <= 0
- formation excluding 2024-11 return <= 0
- OOS positive-month concentration 35.55% > 25%

Diagnostic status: `blocked`.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
