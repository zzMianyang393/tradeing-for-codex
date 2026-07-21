# Restricted Combo Drawdown Anatomy Audit

Date: 2026-07-13

Descriptive post-hoc attribution. No allocation or strategy rule is changed.

## Maximum Drawdown Episodes

| Pair | Peak | Trough | Recovery | Drawdown | Days | Classification |
| --- | --- | --- | --- | ---: | ---: | --- |
| `low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1` | 2025-08-09 | 2026-05-04 | not recovered | 17.378571% | 268 | `minor_additive_loss` |
| `persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1` | 2025-10-10 | 2026-07-09 | not recovered | 8.951689% | 272 | `minor_additive_loss` |

## Component Attribution

### `low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1`

| Component | Peak-to-Trough PnL | Average Exposure | Standalone Max DD |
| --- | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | -31529.298947 | 20.40% | 17.291636% |
| `persistent_uptrend_ema20_reclaim_v1` | -572.342598 | 0.23% | 2.112996% |

- joint negative days: 5/268 (1.87%)
- smaller loss share: 1.78%
- reconciliation error: +0.000002
- action: `retain_without_common_failure_flag`

### `persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1`

| Component | Peak-to-Trough PnL | Average Exposure | Standalone Max DD |
| --- | ---: | ---: | ---: |
| `persistent_uptrend_ema20_reclaim_v1` | -687.378753 | 0.26% | 2.112996% |
| `ema_continuation_short_downtrend_v1` | -10729.434730 | 7.20% | 8.419929% |

- joint negative days: 3/272 (1.10%)
- smaller loss share: 6.02%
- reconciliation error: -0.000004
- action: `retain_without_common_failure_flag`

## Safety

- strict combo gate results remain unchanged
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
