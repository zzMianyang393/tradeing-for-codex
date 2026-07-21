# EMA Short Downtrend Capital Simulation Research Card

Date: 2026-07-13

Research ID: `ema_short_downtrend_capital_constrained_v1`

Status: `pre_registered_read_only_portfolio_simulation`

## Frozen Component

- source: 4h EMA20 / EMA50 crossover
- direction: short only
- compatible regime: completed-4h `趋势下行`
- entry: next 15m open after completed bearish crossover
- exit: opposite completed crossover or five-day time exit
- source event timestamps and prices are unchanged

This component was identified after the regime inventory showed 24 positive OOS events. It is therefore post-hoc and requires a genuinely future validation window even if the current diagnostic passes.

## Capital Rules

- independent initial capital per split: `100,000 USDT`
- maximum positions: 5
- target collateral per position: 20% of current equity
- leverage: none
- one active position per symbol
- entry and exit costs: 0.08% each side
- no rebalancing
- intraday exits before later entries
- same-time capacity priority: symbol ascending
- daily close mark-to-market

Short collateral value follows the frozen source return convention `entry_price / mark_price`, after entry cost; exit cost is applied when collateral is released.

## Stress And Gate

Formation is also calculated after excluding 2024-11.

The component cannot advance unless:

- formation and OOS total returns are both positive
- formation excluding 2024-11 remains positive
- at least 15 OOS positions are accepted
- OOS maximum drawdown is no more than 20%
- OOS positive-month concentration is no more than 25%

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
- no execution entry integration
- no optimizer or parameter scan

