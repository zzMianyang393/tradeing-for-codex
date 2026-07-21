# Prospective Signal Conflict Arbitration

Date: 2026-07-14

Pre-registered signal-state arbitration. No prices, exits, outcomes, positions, or orders were evaluated.

- common data cutoff: `2026-07-13 08:15:00`
- raw signals: 28
- deduplicated signals: 23
- suppressed repeats: 5
- arbitration snapshots: 23
- independent observations: 18
- capped same-direction consensus: 1
- opposite-direction lockouts: 4

## Frozen Rules

- Suppress repeated same-component same-symbol triggers while its fixed validity window remains active.
- Opposite active directions on one symbol create a conflict lockout with zero notional votes.
- Two or more same-direction components create one capped consensus vote; leverage is never added.
- One active component creates one independent observation vote.
- On one symbol, Donchian trend baseline and EMA20 reclaim share one 10-day uptrend trend-sleeve window.
- A later signal from the other uptrend component records co-activation but never extends that sleeve window or adds a vote.

## Safety

- `prices_evaluated = false`
- `outcomes_evaluated = false`
- `exits_evaluated = false`
- `positions_opened = false`
- `orders_created = false`
- `safe_to_enable_trading = false`
