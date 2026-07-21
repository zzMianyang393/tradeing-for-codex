# Two-Regime Shared-Capital Combo Simulation

Date: 2026-07-13

Components share one 100,000 USDT account, five positions, and one-position-per-symbol exposure control.

## Portfolio Results

| Window | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Month Concentration |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `formation` | 164 | 79 | 85 | +96.021762% | 24.764900% | 56.96% | 38.49% | 100.00% | 45.97% |
| `formation_excluding_2024_11` | 107 | 65 | 42 | +3.571604% | 28.193800% | 50.77% | 31.93% | 100.00% | 31.42% |
| `oos` | 189 | 80 | 109 | -13.499885% | 46.540200% | 51.25% | 67.49% | 100.00% | 21.52% |

## OOS Component Attribution

| Component | Accepted | Rejected | PnL | Return Contribution | Win |
| --- | ---: | ---: | ---: | ---: | ---: |
| `donchian_long_uptrend` | 31 | 16 | -7952.197341 | -7.952197% | 48.39% |
| `rsi_rebound_downtrend` | 49 | 93 | -5547.687503 | -5.547688% | 53.06% |

## Decision

- total return <= 0
- maximum drawdown 46.54% > 20%

Diagnostic status: `blocked`.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
