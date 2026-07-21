# Prospective Legacy Weak-Factor Preflight

Date: 2026-07-14

Rejected standalone strategies are evaluated only as reusable weak-signal triggers.

- common data cutoff: `2026-07-13 08:15:00`
- source weak factors: 5
- raw signals: 22
- declared-regime-compatible raw signals: 7
- fixed-window signals: 6
- suppressed repeats: 1
- interactions with existing factors within 24h: 6

## Factor Decisions

| Factor | Raw | Regime-compatible | Fixed-window | Exact overlap | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| `donchian_atr_trend_baseline` | 2 | 1 | 1 | 0 | `eligible_for_shadow_observation_only` |
| `daily_bb_mean_revert` | 0 | 0 | 0 | 0 | `inactive_short_window_keep_observing` |
| `daily_rsi_mean_revert` | 1 | 0 | 0 | 0 | `signals_only_in_declared_incompatible_regimes` |
| `daily_trend_pullback` | 3 | 0 | 0 | 0 | `signals_only_in_declared_incompatible_regimes` |
| `4h_ema_crossover` | 16 | 6 | 5 | 5 | `semantic_duplicate_observed_do_not_add` |

## Safety

- Standalone approval remains forbidden.
- `forward_prices_evaluated = false`
- `outcomes_evaluated = false`
- `registry_changed = false`
- `safe_to_enable_trading = false`
