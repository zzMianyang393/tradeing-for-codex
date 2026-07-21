# Donchian Uptrend Capital-Constrained Simulation

Date: 2026-07-13

Frozen Donchian long events are included only when the completed-4h entry label is `趋势上行`.

## Results

| Window | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Positive-Month Concentration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `formation` | 105 | 52 | 53 | +59.371245% | 20.507900% | 53.85% | 26.98% | 100.00% | 43.63% |
| `formation_excluding_2024_11` | 60 | 42 | 18 | -4.270040% | 24.877400% | 47.62% | 20.68% | 100.00% | 32.26% |
| `oos` | 47 | 32 | 15 | -5.380682% | 22.985400% | 46.88% | 25.99% | 100.00% | 46.92% |

## Decision

- total return <= 0
- maximum drawdown 22.99% > 20%
- positive-month concentration 46.92% > 25%
- formation excluding 2024-11 return <= 0

Diagnostic status: `blocked`.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
