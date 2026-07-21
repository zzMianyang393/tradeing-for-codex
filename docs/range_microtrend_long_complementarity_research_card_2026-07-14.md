# Range Microtrend Long Complementarity Research Card

Date: 2026-07-14

## Frozen Question

Determine whether the post-hoc `weekly_range_microtrend_continuation_v1_long` sleeve is distinct from the existing low-volatility drift breakout, persistent-uptrend EMA20 reclaim, EMA downtrend continuation short, and daily volume-shock short weak features.

## Frozen Method

- common window: `2025-01-01` through `2026-07-10`
- constant 28-symbol universe
- unchanged 10% standalone allocation and existing execution assumptions
- metrics: active-union daily return correlation, monthly return correlation, active-day Jaccard, negative-day overlap coefficient, and same-symbol interval overlap
- strict thresholds are inherited unchanged from prior complementarity audits

Economic duplication and operational overlap are reported separately. Because the range-long sleeve was found after the frozen bidirectional rule failed, no result may authorize a historical combo simulation.

## Safety

- prospective pair comparison only
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
