# Daily Volume-Shock Reversal Preflight Card

Date: 2026-07-13

Status: frozen event-inventory preflight; future returns are prohibited.

## Candidate Mechanism

A completed daily candle is a volume-shock exhaustion event when all are true:

- current volume is at least 2.5 times the mean volume of the prior 20 completed days
- current true range is at least 1.5 times the prior completed 14-day Wilder ATR
- close location is in the bottom 20% of the daily range for a prospective long reversal, or the top 20% for a prospective short reversal
- signal becomes available only after the daily candle closes

This preflight records event timestamps and directions only. It must not read any forward price, return, stop, or exit outcome.

## Panels

- primary: BTC and ETH constant full-window universe
- secondary: symbols with at least 98% 15m coverage inside each observed fold
- observed inventory window: 2024-01-01 through 2026-07-10

## Event-Coverage Gate

Research-card creation is allowed only when all are true:

- primary panel has at least 15 events
- primary events occur in at least 4 of 5 folds
- secondary panel has at least 60 events
- secondary panel has at least 3 folds containing 10 or more events
- both long and short directions each contribute at least 20% of secondary events
- no single month contributes more than 25% of secondary events

Passing this gate does not imply profitability and cannot approve a strategy.

## Safety

- no forward returns are computed
- no parameter grid is allowed
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
