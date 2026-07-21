# Latest Rejected Feature Semantic Review

## Scope

This review classifies four strategies rejected on 2026-07-15 for possible
research-layer reuse. It does not reverse their standalone rejection and does
not approve any feature for paper trading.

| Research id | Reuse role | Why | Prohibited use |
|---|---|---|---|
| `daily_williams_r_range_reversion` | `context_label` | Both formation and OOS were negative and concentrated. The oversold/range condition may describe context, but cannot vote direction. | Directional entry or standalone strategy |
| `daily_parabolic_sar_trend` | `directional_weak_signal` | OOS mean was positive, but the evidence failed the concentration rule. It can only be a low-weight trend vote with a concentration penalty. | Standalone strategy, unpenalized weight, paper trading |
| `daily_atr_expansion_breakout` | `risk_filter_candidate` | OOS was materially negative after cost and formation was concentrated. It can describe failed-breakout risk, not a continuation entry. | Breakout direction signal or standalone strategy |
| `daily_volume_confirmed_breakout` | `risk_filter_candidate` | Both splits were negative with weak win rate and concentration. It can warn against volume-confirmed breakout exposure. | Directional breakout signal or standalone strategy |

## Common boundaries

- All four retain `eligible_for_paper=false` and `allowed_as_standalone_strategy=false`.
- A role assignment is not outcome evidence and does not make a combined
  strategy backtest-ready.
- Any later combination must use frozen underlying definitions, apply the
  regime gate, assess factor correlation, and wait for the relevant sealed
  prospective evidence before evaluation.
