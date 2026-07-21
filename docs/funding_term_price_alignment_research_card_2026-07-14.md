# Funding-Term Price Alignment Research Card

Date: 2026-07-14

## Distinction

This is not the rejected four-leg `long spot / short perpetual` carry trade and does not attempt to collect one settlement. It uses the already-settled seven-day funding mean as a low-frequency sentiment state for one directional perpetual position.

The return-free preflight produced 225 events across 24 symbols and 47 weeks, including 144 long and 81 short events.

## Frozen Signal

- window: `2025-01-01` through `2026-07-10`
- universe: constant 28-symbol price panel with available funding history
- schedule: Monday 00:15 UTC
- funding indicator: mean of the latest 21 settled funding observations
- historical context: prior 180 days, excluding the current observation
- high state: positive funding mean at or above the prior 80th percentile
- low state: negative funding mean at or below the prior 20th percentile
- long: high state, positive completed prior-seven-day price change, and completed 4h label in uptrend or `low_volatility_drift_v2`
- short: low state, negative completed prior-seven-day price change, and completed 4h label in downtrend or `low_volatility_drift_v2`
- no parameter grid or absolute funding threshold

## Frozen Execution

- entry: the 00:15 UTC 15m open after the settled 00:00 funding observation is available
- priority: greatest normalized distance beyond the relevant funding threshold, deterministic symbol tie-break
- 10% of shared equity per position, maximum five positions, one per symbol
- stop: 2 completed-daily ATR(14)
- exit: first completed 4h label incompatible with the direction, or seven days, whichever occurs first
- one-leg round-trip cost: 0.16%

## Frozen Screen

- at least 120 accepted positions
- aggregate net return greater than 0%
- maximum drawdown at most 20%
- at least 2/3 positive half-year folds
- top positive month share at most 25%
- each directional sleeve has at least 40 accepted positions and positive contribution

## Safety

- a passing historical screen only freezes a prospective candidate
- observations stop at `2026-07-10`
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
