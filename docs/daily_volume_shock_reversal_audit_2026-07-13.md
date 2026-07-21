# Daily Volume-Shock Reversal Audit

Date: 2026-07-13

The signal was frozen after a return-free event preflight.

## Primary Constant-Universe Result

- symbols: 28
- accepted positions: 127
- return: +7.813065%
- maximum drawdown: 13.971200%
- win rate: 53.54%
- average / peak exposure: 6.01% / 53.29%
- positive folds: 2/3
- top positive month share: 13.54%

## Fold Returns

| 2025-H1 | 2025-H2 | 2026-H1 |
| ---: | ---: | ---: |
| +3.994358% | -2.274826% | +6.085289% |

## Direction Attribution

| Direction | Accepted | Rejected | Return Contribution | Win |
| --- | ---: | ---: | ---: | ---: |
| `daily_volume_shock_reversal_v1_long` | 53 | 2 | -1.676710% | 56.60% |
| `daily_volume_shock_reversal_v1_short` | 74 | 19 | +9.489774% | 51.35% |

## Decision

- daily_volume_shock_reversal_v1_long return contribution -1.676710% <= 0%

## Post-Hoc Direction Watchlist

- `daily_volume_shock_reversal_v1_short`: 74 accepted, +9.489774% contribution, 3/3 positive folds; standalone use prohibited.

Short-only shared-capital diagnostic: 75 accepted, +9.376166% return, 11.839900% max DD, 3/3 positive folds, 19.03% month concentration.

Status: `observed_rejected`.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
