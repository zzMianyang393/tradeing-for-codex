# Weekly Range Microtrend Continuation Audit

Date: 2026-07-14

Frozen observed audit inside `mean_reverting_range_v2` only.

## Aggregate

- accepted positions: 145
- net return: +3.596112%
- maximum drawdown: 2.028000%
- win rate: 57.93%
- positive folds: 1/3
- top positive month share: 20.74%
- status: `observed_rejected`

## Direction Attribution

| Sleeve | Accepted | Return Contribution | Win |
| --- | ---: | ---: | ---: |
| `weekly_range_microtrend_continuation_v1_long` | 64 | +1.461969% | 65.62% |
| `weekly_range_microtrend_continuation_v1_short` | 81 | +2.134143% | 51.85% |

## Fold Returns

- `2025-H1`: -0.395689%
- `2025-H2`: +4.651970%
- `2026-H1`: -0.126404%

## Decision Reasons

- positive folds 1/3 < 2/3

## Post-Hoc Sleeve Diagnostics

- `weekly_range_microtrend_continuation_v1_long`: 76 accepted, +2.034988% return, 2.891700% max DD, 2/3 positive folds, 20.09% month concentration; standalone use prohibited.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
