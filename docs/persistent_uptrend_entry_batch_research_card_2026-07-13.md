# Persistent Uptrend Entry Batch Research Card

Date: 2026-07-13

Status: frozen observed-data diagnostic; not prospective validation.

## Motivation

The completed-4h uptrend label is not a stable unconditional long context. Its first ten days have negative forward drift, while runs older than ten days show positive aggregate drift but still fail in later folds. This batch tests whether fixed entry timing can isolate a useful weak component without changing the label definition.

## Data And Panels

- observed data only: 2024-01-01 through 2026-07-10
- primary panel: constant full-window universe (`BTC-USDT-SWAP`, `ETH-USDT-SWAP`)
- secondary panel: symbols with at least 98% 15m coverage inside each fold
- folds: 2024-H1, 2024-H2, 2025-H1, 2025-H2, 2026-H1
- no signal or return after 2026-07-10 may be read

## Frozen Components

### Persistent EMA20 Reclaim

- completed 4h local label must remain uptrend for more than 60 bars (10 days)
- BTC completed-4h label must also be uptrend
- prior completed close is at or below EMA20 and current completed close reclaims EMA20
- enter at the first 15m open after signal availability
- exit on first completed 4h close below EMA20, 2 ATR stop, or 10 days

### Persistent 20-Bar Breakout

- completed 4h local label must remain uptrend for more than 60 bars (10 days)
- BTC completed-4h label must also be uptrend
- current completed close exceeds the prior 20 completed 4h highs
- enter at the first 15m open after signal availability
- exit on first completed 4h close below EMA20, 2 ATR stop, or 10 days

### Daily MA Pullback Reclaim

- daily EMA50 must be above daily EMA200
- local and BTC completed-4h labels must both be uptrend at signal availability
- prior daily close is at or below daily EMA20 and current daily close reclaims EMA20
- enter at the first 15m open after the completed daily candle
- exit on first completed daily close below EMA50, 2 ATR stop, or 20 days

## Capital And Cost

- 10% equity per position
- maximum 5 concurrent positions in the expanding panel
- one position per symbol
- 0.16% round-trip friction
- no leverage, pyramiding, averaging down, grid, or martingale

## Screen

Primary constant-universe panel must have:

- at least 30 accepted positions
- positive aggregate return after cost
- maximum drawdown no greater than 20%
- at least 3 of 5 positive folds
- top positive month contribution no greater than 25%

The expanding panel is diagnostic and cannot rescue a failed primary panel.

## Interpretation

The 10-day persistence threshold was discovered in the preceding observed-data structure audit. Any passing component is therefore post-hoc and must be frozen for prospective validation from a future untouched start date. No component can be approved for paper trading from this batch.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
