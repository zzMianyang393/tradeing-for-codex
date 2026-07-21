# Daily RSI Downtrend Rebound Regime-Conditioned Audit

Date: 2026-07-13

## Purpose

This audit reuses the fixed `daily_rsi_mean_revert` rule and changes only the declared compatible regime.

Old interpretation:

- RSI oversold as a `震荡` mean-reversion rule

Corrected research interpretation:

- RSI oversold as a `趋势下行` rebound rule

This is a semantic repair, not parameter tuning.

## Output

Machine-readable output:

- `reports/daily_rsi_downtrend_rebound_regime_conditioned_audit.json`

## Frozen Rule

- Daily RSI(14) below 35
- Long next daily open
- Exit after RSI recovers to 50 or after maximum 10 days
- Cost floor: `0.16%` round trip
- Compatible regime: completed-4h `趋势下行`

## Results

Formation declared-compatible events:

- events: `59`
- net return: `+446.486403%`
- mean return: `+7.567566%`
- median return: `+5.879564%`
- win rate: `69.49%`
- profit factor: `5.674902`

OOS declared-compatible events:

- events: `142`
- net return: `+302.720049%`
- mean return: `+2.131831%`
- median return: `+2.096734%`
- win rate: `56.34%`
- profit factor: `1.438360`

Verdict:

- `regime_conditioned_candidate`
- `eligible_as_combo_directional_feature = true`
- `requires_regime_gate = true`

## Caveat

This profile was discovered after the regime inventory showed that RSI events do not belong to `震荡`.

Therefore it may enter combo research as a weak feature, but it is not approved for standalone trading or paper trading. The next validation step must treat this as a post-hoc semantic repair and require future-window evidence before any escalation.

Safety gates remain:

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
