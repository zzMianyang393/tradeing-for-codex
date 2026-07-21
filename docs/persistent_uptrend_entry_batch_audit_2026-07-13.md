# Persistent Uptrend Entry Batch Audit

Date: 2026-07-13

Post-hoc observed-data diagnostic. The constant BTC/ETH universe is the primary panel.

## Primary Constant-Universe Results

| Component | Accepted | Return | Max DD | Positive Folds | Month Concentration | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `persistent_uptrend_ema20_reclaim` | 90 | +4.697309% | 2.113000% | 3/5 | 37.97% | `weak_feature_watchlist_concentration_penalty` |
| `persistent_uptrend_20bar_breakout` | 29 | +2.939115% | 3.246100% | 2/5 | 41.07% | `observed_rejected` |
| `daily_ma_pullback_reclaim` | 6 | -2.995731% | 4.054600% | 1/5 | 100.00% | `observed_rejected` |

## Secondary Fold-Eligible Results

| Component | Accepted | Return | Max DD | Positive Folds | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| `persistent_uptrend_ema20_reclaim` | 230 | -3.545919% | 9.956200% | 2/5 | `observed_rejected` |
| `persistent_uptrend_20bar_breakout` | 81 | -1.340803% | 7.097500% | 2/5 | `observed_rejected` |
| `daily_ma_pullback_reclaim` | 16 | -6.785441% | 8.365200% | 1/5 | `observed_rejected` |

## Primary Fold Returns

| Component | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `persistent_uptrend_ema20_reclaim` | +3.369691% | +0.656144% | -0.195433% | +1.409856% | -0.580533% |
| `persistent_uptrend_20bar_breakout` | +1.832705% | -0.326140% | -0.051614% | +1.878634% | -0.401461% |
| `daily_ma_pullback_reclaim` | -3.433074% | +0.000000% | -0.557466% | +1.016022% | +0.000000% |

## Primary Decisions

- `persistent_uptrend_ema20_reclaim`: retain only as a directional weak-feature watchlist item with a concentration penalty; standalone use prohibited
- `persistent_uptrend_20bar_breakout`: accepted positions 29 < 30; positive folds 2/5 < 3/5; top positive month share 41.07% > 25%
- `daily_ma_pullback_reclaim`: accepted positions 6 < 30; aggregate return -2.995731% <= 0%; positive folds 1/5 < 3/5; top positive month share 100.00% > 25%

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
