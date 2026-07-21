# Volume-Shock Short Complementarity Research Card

Date: 2026-07-13

Status: frozen post-hoc weak-feature complementarity audit.

## Scope

Compare `daily_volume_shock_reversal_v1_short` with the three existing weak components on one common 2025-01-01 through 2026-07-10 window and the constant 28-symbol late universe.

The volume-shock short side was discovered after the pre-registered bidirectional rule failed because its long side lost money. Therefore, this audit can create only pair watchlist evidence. It cannot authorize a shared-capital combo simulation.

## Normalization

- 100,000 USDT independent account per component
- 10% equity per position
- maximum five positions
- one position per symbol
- existing event costs and exits unchanged
- no signal, allocation, or threshold changes

## Fixed Pair Metrics

- daily return correlation on the union of active days
- compounded monthly return correlation
- active-day Jaccard overlap
- negative-day overlap coefficient
- event interval and same-symbol overlap

## Watchlist Gate

A pair may be retained for future prospective comparison only when:

- each side has at least 30 accepted positions on the common window
- each side has positive standalone return
- active-union daily correlation is no greater than 0.35
- monthly correlation is no greater than 0.50
- negative-day overlap coefficient is no greater than 0.35
- active-day Jaccard overlap is no greater than 0.50

Passing creates no combo-backtest permission because the volume-shock short direction is post-hoc.

## Safety

- observed data stops at 2026-07-10
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
