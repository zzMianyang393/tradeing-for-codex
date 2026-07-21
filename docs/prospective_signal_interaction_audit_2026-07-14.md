# Prospective Signal Interaction Audit

Date: 2026-07-14

Signal metadata only. No prices, exits, positions, or outcomes were evaluated.

- data cutoff: `2026-07-13 08:15:00`
- raw signals: 28
- active candidates: 5
- inactive candidates: 2
- same-symbol interactions within 24h: 8
- same-direction consensus: 3
- opposite-direction conflicts: 5

## Registered Pairs

| Pair | Shared days | 24h overlaps | Consensus | Conflicts | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| `combo::low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1` | 0 | 0 | 0 | 0 | `no_interaction_yet` |
| `combo::persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1` | 0 | 0 | 0 | 0 | `no_interaction_yet` |
| `pair_watchlist::daily_volume_shock_reversal_v1_short__ema_continuation_short_downtrend_v1` | 0 | 0 | 0 | 0 | `no_interaction_yet` |
| `pair_watchlist::daily_volume_shock_reversal_v1_short__persistent_uptrend_ema20_reclaim_v1` | 0 | 0 | 0 | 0 | `no_interaction_yet` |
| `pair_watchlist::weekly_cross_sectional_momentum_v1_short__persistent_uptrend_ema20_reclaim_v1` | 0 | 0 | 0 | 0 | `no_interaction_yet` |
| `pair_watchlist::weekly_range_microtrend_continuation_v1_long__daily_volume_shock_reversal_v1_short` | 0 | 0 | 0 | 0 | `no_interaction_yet` |
| `pair_watchlist::weekly_range_microtrend_continuation_v1_long__ema_continuation_short_downtrend_v1` | 1 | 0 | 0 | 0 | `interaction_observed` |
| `pair_watchlist::weekly_range_microtrend_continuation_v1_long__persistent_uptrend_ema20_reclaim_v1` | 0 | 0 | 0 | 0 | `no_interaction_yet` |

## Emergent Interactions

| Component pair | 24h overlaps | Consensus | Conflicts | Class |
| --- | ---: | ---: | ---: | --- |
| `ema_continuation_short_downtrend_v1__low_volatility_drift_bb_breakout_fixed_risk_v1` | 1 | 1 | 0 | `consensus_candidate` |
| `ema_continuation_short_downtrend_v1__weekly_cross_sectional_momentum_v1_short` | 2 | 2 | 0 | `consensus_candidate` |
| `low_volatility_drift_bb_breakout_fixed_risk_v1__weekly_range_microtrend_continuation_v1_long` | 5 | 0 | 5 | `conflict_candidate` |

## Safety

- Co-activation does not authorize a backtest or trade.
- `prices_evaluated = false`
- `outcomes_evaluated = false`
- `forward_returns_evaluated = false`
- `safe_to_enable_trading = false`
