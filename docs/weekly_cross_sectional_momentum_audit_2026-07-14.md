# Weekly Cross-Sectional Momentum Audit

Date: 2026-07-14

Constant 28-symbol, weekly long-short observed audit.

## Aggregate

- candidate events: 468
- accepted positions: 468
- return: +9.428570%
- maximum drawdown: 17.396700%
- win rate: 45.73%
- average / peak exposure: 53.85% / 61.78%
- capital turnover: 51.7140x
- positive folds: 2/3
- top positive month share: 8.37%

## Fold Returns

| 2025-H1 | 2025-H2 | 2026-H1 |
| ---: | ---: | ---: |
| +12.667345% | +1.852467% | -0.020453% |

## Sleeve Attribution

| Sleeve | Accepted | Rejected | Return Contribution | Win |
| --- | ---: | ---: | ---: | ---: |
| `weekly_cross_sectional_momentum_v1_long` | 234 | 0 | -56.723079% | 36.75% |
| `weekly_cross_sectional_momentum_v1_short` | 234 | 0 | +66.151649% | 54.70% |

## Decision

- weekly_cross_sectional_momentum_v1_long return contribution -56.723079% <= 0%

## Post-Hoc Sleeve Watchlist

- `weekly_cross_sectional_momentum_v1_short`: 234 accepted, +66.151649% contribution, 3/3 positive folds; standalone use prohibited.

Short-only diagnostic: 234 accepted, +76.810624% return, 14.434100% max DD, 3/3 positive folds, 11.11% month concentration.

Status: `observed_rejected`.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
