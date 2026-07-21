# Daily Volume-Shock Reversal Research Card

Date: 2026-07-13

Status: frozen after return-free event preflight; observed outcome audit pending.

## Primary Universe And Window

- primary universe: intersection of symbols with at least 98% 15m coverage in 2025-H1, 2025-H2, and 2026-H1
- expected primary universe: 28 symbols
- primary observed window: 2025-01-01 through 2026-07-10
- fixed folds: 2025-H1, 2025-H2, 2026-H1 through 2026-07-10
- BTC/ETH full-window events remain a sample-size diagnostic only

The shortened constant universe was selected from event coverage only. No forward return was read during preflight.

## Frozen Signal

On a completed daily candle:

- volume is at least 2.5 times the mean of the prior 20 completed daily volumes
- true range is at least 1.5 times the prior completed 14-day Wilder ATR
- close in the bottom 20% of the range generates a long reversal
- close in the top 20% of the range generates a short reversal
- enter at the first 15m open after the daily candle closes

## Frozen Exit And Risk

- fixed maximum holding period: 3 days
- hard stop: 2 times the prior completed daily ATR
- round-trip cost: 0.16%
- no second position in the same symbol before exit
- 10% equity per position
- maximum five concurrent positions
- one position per symbol
- no leverage, averaging down, grid, or martingale

## Outcome Gate

The primary panel must satisfy all conditions:

- at least 60 accepted positions
- positive aggregate return after cost
- maximum drawdown no greater than 20%
- at least 2 of 3 positive folds
- top positive-month contribution no greater than 25%
- long and short sides each have at least 20 accepted positions
- long and short sides each contribute positive realized PnL

A passing result remains an observed historical candidate and requires prospective validation. It does not open paper or production gates.

## Safety

- no parameter grid
- no outcome-dependent threshold changes
- observed data stops at 2026-07-10
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
