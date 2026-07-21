# High-Positive Funding Long Risk Filter Audit

Date: 2026-07-14

Post-hoc meta-only diagnostic. No historical filtered backtest is authorized.

## Aggregate

- high-positive events: 189
- high-positive mean: +0.149317%
- other-state mean: +0.800298%
- high-minus-other gap: -0.650981pp
- status: `posthoc_filter_rejected`

## Components

| Component | High Events | High Mean | Other Events | Other Mean | Gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1_long` | 147 | +0.206032% | 493 | +0.849112% | -0.643080pp |
| `persistent_uptrend_ema20_reclaim_v1` | 28 | +0.054602% | 22 | +0.229772% | -0.175170pp |
| `weekly_range_microtrend_continuation_v1_long` | 14 | -0.256753% | 46 | +0.550009% | -0.806762pp |

## High-Positive Funding Folds

- `2025-H1`: 18 events, -1.358468% mean
- `2025-H2`: 78 events, +0.362440% mean
- `2026-H1`: 76 events, +0.379183% mean

## Decision Reasons

- high-positive mean +0.149317% >= 0%
- qualified negative folds 1/3 < 2/3

## Safety

- hard filter allowed: `false`
- historical filtered backtest authorized: `false`
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
