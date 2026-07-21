# Donchian Uptrend Capital Simulation Research Card

Date: 2026-07-13

Research ID: `donchian_uptrend_capital_constrained_v1`

Status: `pre_registered_read_only_portfolio_simulation`

## Purpose

Evaluate the frozen Donchian + ATR long component only in its declared completed-4h `趋势上行` regime using the same shared-capital rules as the downtrend rebound component.

## Frozen Source Rule

- Donchian breakout: 20 completed daily candles
- ATR: 14 completed daily candles
- fixed stop: 2 ATR
- maximum hold: 10 days
- direction in this card: long only
- compatible regime: `entry_regime == 趋势上行`
- source entry and exit timestamps/prices remain unchanged

## Frozen Portfolio Rules

- initial capital: `100,000 USDT` independently for formation and OOS
- maximum concurrent positions: 5
- target allocation: 20% of current equity per accepted position
- leverage: none
- entry cost: 0.08%
- exit cost: 0.08%
- no rebalancing
- intraday exits occur before later entries
- daily marked-to-market equity uses completed daily closes
- same-time capacity priority: symbol ascending

## Fixed Stress Test

Run formation once with all compatible long events and once after excluding events signaled in `2024-11`. The exclusion is a concentration diagnostic, not an alternative deployable rule.

## Advancement Gate

- OOS return must be positive
- OOS maximum drawdown must be no more than 20%
- at least 20 OOS positions must be accepted
- OOS top positive month contribution must be no more than 25%
- formation excluding 2024-11 must remain profitable

Passing would only admit the component to a later shared-capital regime portfolio study. It would not approve paper trading.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
- no execution entry integration
- no parameter scan
- no dynamic optimizer

