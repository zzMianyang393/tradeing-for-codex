# Low-Volatility Drift Breakout Research Card

Date: 2026-07-13

## Status

This hypothesis is post-hoc. It was created after the range-structure audit
showed negative mean-reversion expectancy at BB extremes. Historical results can
only decide whether it is worth prospective observation.

## Frozen Rule

- regime: `low_volatility_drift_v2` only
- signal timeframe: completed 4-hour candles
- Bollinger Band: 20 periods, 2 standard deviations
- long: close crosses above the upper band
- short: close crosses below the lower band
- entry: first available 15-minute open after the completed 4-hour signal
- exit: completed close reaches the opposite side of the middle-band condition
  (long closes at or below middle; short closes at or above middle), or 3-day time
  exit
- stop: 2 x signal ATR(14)
- cost: 0.16% round trip
- one event per symbol; five-account-position cap; 20% allocation per event

## Historical Screen

Use the frozen five half-year observed buckets and the same requirements:

- at least 30 accepted positions
- aggregate return greater than 0%
- maximum drawdown at most 20%
- at least 3/5 positive half-year buckets
- top positive month share at most 25%

Passing this screen sets only `posthoc_prospective_candidate`. It does not make
the component eligible for combination backtests or paper trading.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

