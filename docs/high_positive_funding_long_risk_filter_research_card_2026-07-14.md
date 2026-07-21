# High-Positive Funding Long Risk Filter Research Card

Date: 2026-07-14

## Post-Hoc Hypothesis

The frozen funding-term price-alignment rule showed that high-positive funding aligned with long regimes lost money, while the apparent short benefit was concentrated in early 2025. This audit tests whether high-positive seven-day funding is a reusable crowding warning for existing long weak features.

## Frozen Inputs

- existing long events only; no signal, entry, exit, cost, or allocation is changed
- components: low-volatility drift breakout long events, persistent-uptrend EMA20 reclaim, and weekly range microtrend continuation long
- funding state: latest 21 settled observations versus the prior 180-day 80th percentile, identical to `funding_term_price_alignment_v1`
- observed window: `2025-01-01` through `2026-07-10`
- analysis uses event-level net outcomes and half-year buckets

## Frozen Diagnostic Screen

The state may enter the prospective risk-filter watchlist only if:

- at least 30 high-positive-funding events exist across components
- their aggregate mean net event outcome is negative
- their mean is at least 0.25 percentage points worse than non-high events
- the high-positive subset has negative mean outcome in at least 2/3 half-year buckets

Passing does not retroactively remove trades or authorize a filtered backtest. It only creates a prospective no-trade-filter observation.

## Safety

- post-hoc diagnostic only
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
