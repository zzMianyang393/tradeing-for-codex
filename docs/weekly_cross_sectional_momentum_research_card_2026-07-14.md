# Weekly Cross-Sectional Momentum Research Card

Date: 2026-07-14

Status: frozen observed-data audit pending.

## Distinction From Rejected Time-Series Momentum

The rejected rule used BTC/ETH 90-day absolute momentum, opened only long positions, and held for 30 days. This rule instead ranks a constant 28-symbol universe by relative 28-day return and holds simultaneous long and short sleeves for seven days.

## Universe And Window

- constant universe: intersection of symbols with at least 98% 15m coverage in 2025-H1, 2025-H2, and 2026-H1
- expected symbols: 28
- observed window: 2025-01-01 through 2026-07-10
- folds: 2025-H1, 2025-H2, and 2026-H1 through 2026-07-10

## Frozen Signal

- rebalance timestamp: Monday 00:00 UTC
- ranking input: return from the close 28 calendar days earlier to the latest completed daily close
- long the three highest-ranked symbols
- short the three lowest-ranked symbols
- no volatility, funding, OI, or regime filter
- enter at the first 15m open after ranking data becomes available

## Frozen Exit And Risk

- fixed maximum holding period: seven days
- hard stop: two times the completed daily ATR(14)
- round-trip cost: 0.16% per position
- 10% equity per position
- maximum six concurrent positions
- one position per symbol
- no leverage, averaging down, grid, martingale, or parameter grid

## Outcome Gate

- at least 240 accepted positions
- positive aggregate return after cost
- maximum drawdown no greater than 20%
- at least 2 of 3 positive folds
- top positive-month contribution no greater than 25%
- long and short sleeves each have at least 100 accepted positions
- long and short sleeves each contribute positive realized PnL

A passing result remains historical and requires prospective validation. No paper or production gate may open.

## Safety

- observed data stops at 2026-07-10
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
