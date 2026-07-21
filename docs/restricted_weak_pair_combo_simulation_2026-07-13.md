# Restricted Weak-Pair Combo Simulation

Date: 2026-07-13

Post-hoc shared-capital diagnostic. Only complementarity-approved pairs are included.

## Aggregate Results

| Pair | Accepted | Return | Max DD | DD Excess | Return/DD | Positive Folds | Month Concentration | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1` | 865 | +68.241452% | 17.378600% | +0.087000pp | 3.9268 | 4/5 | 7.26% | `observed_combo_rejected` |
| `persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1` | 157 | +16.121283% | 8.951700% | +0.531800pp | 1.8009 | 4/5 | 24.95% | `observed_combo_rejected` |

## Fold Returns

| Pair | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1` | +5.340173% | +31.508298% | +19.927134% | -4.502499% | +5.854531% |
| `persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1` | +3.369691% | +0.656144% | +4.647013% | +12.280990% | -4.367727% |

## Component Attribution

### `low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1`

| Component | Accepted | Rejected | Return Contribution | Win |
| --- | ---: | ---: | ---: | ---: |
| `low_volatility_drift_bb_breakout_fixed_risk_v1` | 780 | 523 | +62.730072% | 40.26% |
| `persistent_uptrend_ema20_reclaim_v1` | 85 | 5 | +5.511380% | 25.88% |

### `persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1`

| Component | Accepted | Rejected | Return Contribution | Win |
| --- | ---: | ---: | ---: | ---: |
| `ema_continuation_short_downtrend_v1` | 67 | 17 | +11.458623% | 53.73% |
| `persistent_uptrend_ema20_reclaim_v1` | 90 | 0 | +4.662659% | 25.56% |

## Decisions

- `low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1`: maximum drawdown 17.378600% > worse standalone 17.291600%
  Post-hoc interpretation: retain as a risk-adjusted combo watchlist item; this does not override the failed pre-registered drawdown gate.
- `persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1`: maximum drawdown 8.951700% > worse standalone 8.419900%
  Post-hoc interpretation: retain as a risk-adjusted combo watchlist item; this does not override the failed pre-registered drawdown gate.

## Safety

- no paper or production gate is opened
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
