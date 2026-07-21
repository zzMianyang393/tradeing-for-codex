# Regime Component Walk-Forward Research Card

Date: 2026-07-13

## Scope

Research four fixed, independent weak-signal prototypes to fill the uptrend and
range-regime gaps. All data through `2026-07-10` are observed research data. The
output is not an unseen validation and cannot approve paper trading.

## Frozen Universe

Use the 28 symbols that passed
`reports/future_window_data_coverage_audit.json`. Keep SEI excluded for
insufficient common history. No symbol may be removed based on return.

## Frozen Components

### `uptrend_donchian_55_20_long`

- completed daily close crosses above the prior 55-day high
- enter at the first 15-minute open available after daily close
- initial stop: 2 x daily ATR(14)
- exit after a completed daily close below the prior 20-day low, or after 30 days
- allowed entry regime: completed-4h `uptrend` only

### `uptrend_supertrend_4h_long`

- completed 4-hour SuperTrend flips upward
- ATR period 10; multiplier 3
- enter at the first 15-minute open available after the completed 4-hour candle
- initial stop: 2 x signal ATR
- exit on a completed downward SuperTrend flip, or after 10 days
- allowed entry regime: completed-4h `uptrend` only

### `range_bb_reversion_4h`

- Bollinger Band period 20; width 2 standard deviations
- completed 4-hour close crossing below lower band enters long
- completed 4-hour close crossing above upper band enters short
- initial stop: 2 x signal ATR(14)
- exit at completed-band midline recovery, or after 3 days
- allowed entry regime: completed-4h `range` only

### `range_rsi_reversion_4h`

- RSI(14) crossing below 30 enters long
- RSI(14) crossing above 70 enters short
- initial stop: 2 x signal ATR(14)
- exit after completed RSI crosses back through 50, or after 3 days
- allowed entry regime: completed-4h `range` only

## Common Execution Rules

- round-trip friction: 0.16%
- initial account equity: 100,000 USDT
- maximum five concurrent positions
- 20% equity allocation per accepted event
- one open position per symbol
- no leverage or reinvestment rule changes
- unused capacity remains cash
- signals and regime labels use completed candles only
- events crossing a fold end are omitted from that fold

## Observed Walk-Forward Buckets

1. `2024-H1`: 2024-01-01 to 2024-06-30
2. `2024-H2`: 2024-07-01 to 2024-12-31
3. `2025-H1`: 2025-01-01 to 2025-06-30
4. `2025-H2`: 2025-07-01 to 2025-12-31
5. `2026-H1`: 2026-01-01 to 2026-07-10

These are stability buckets, not train/test splits. Parameters are never fitted.

## Candidate Screen

A component becomes a historical walk-forward candidate only when all conditions
hold:

1. Aggregate accepted positions are at least 30.
2. Aggregate net portfolio return is greater than 0%.
3. Aggregate maximum drawdown is at most 20%.
4. At least three of five half-year buckets have positive return.
5. The top positive month contributes at most 25% of all positive realized PnL.

Failure does not trigger parameter adjustment. A changed rule requires a new
research card and must not claim the reserved prospective window as untouched.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

