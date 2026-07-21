# 4h EMA Crossover Research Card

Date: 2026-07-13

## Rule

- Resample 15m OHLCV to completed 4h bars.
- EMA20 crossing above EMA50 creates a long signal.
- EMA20 crossing below EMA50 creates a short signal.
- Enter on the next 15m open after the completed 4h signal.
- Exit on opposite completed 4h cross or max 5-day hold.
- Round-trip cost is fixed at 0.16%.

## Split

- Formation: 2024-01-01 to 2024-12-31
- OOS: 2025-01-01 to 2025-07-10

## Required Diagnostics

- Formation and OOS net return.
- Event count and win rate.
- Profit factor.
- Direction counts.
- Monthly and symbol concentration.
- Formation result excluding 2024-11.

## Safety

This is a read-only research audit. It is not approved for standalone, paper, or live trading.
