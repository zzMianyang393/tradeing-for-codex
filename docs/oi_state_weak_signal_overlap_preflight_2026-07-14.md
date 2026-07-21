# OI-State Weak-Signal Overlap Preflight

Date: 2026-07-14

Return-free temporal overlap preflight. No weak-signal outcome was read.

## Aggregate

- OI-state overlaps: 116
- distinct symbols: 25
- components with at least 15 overlaps: 1
- folds with at least 15 overlaps: 2
- preflight pass: `false`

## Components

| Component | Events | OI Overlaps | Rate | Symbols | 2025-H1 | 2025-H2 | 2026-H1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | 973 | 106 | 10.89% | 25 | 77 | 24 | 5 |
| `persistent_uptrend_ema20_reclaim_v1` | 50 | 8 | 16.00% | 2 | 1 | 4 | 3 |
| `ema_continuation_short_downtrend_v1` | 60 | 2 | 3.33% | 2 | 0 | 0 | 2 |

## Safety

- `outcome_fields_read = false`
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
