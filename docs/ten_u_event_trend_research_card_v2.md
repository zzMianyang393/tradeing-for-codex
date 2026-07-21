# 10U Persistent Event Trend 48h v2 — Sealed Research Card

Status: `preregistered_before_sealed_screen_access`

v1 established that a single four-hour range/volume expansion bar usually does not preserve its direction for 24–48 hours. v2 is not a stop-width adjustment. It replaces that failed direction assumption with a twelve-hour persistence state.

## Frozen state machine

1. Detect the unchanged v1 four-hour ignition: true range and quote volume are each at least 2.0 times their preceding 20-bar medians, with a top/bottom-quartile close and a prior-20-bar extreme break.
2. Observe the next three completed 4h bars. For a long, all three closes must remain at or above the ignition midpoint and the third close must finish above the ignition high. For a short, all three closes must remain at or below the midpoint and the third close must finish below the ignition low.
3. After persistence confirmation, wait no more than eight completed 1h bars for one counter-direction close followed by a close beyond the preceding 1h extreme in the intended direction. Enter only at the next 1h open.
4. Cancel if a completed 1h close crosses the original ignition midpoint against the position direction.
5. Use the pullback extreme as structural invalidation and place the hard disaster stop another 0.5 Wilder ATR(14) beyond it. Skip stop distances above 20%.
6. Keep the v1 risk/execution discipline: one position, 15% equity risk, actual stop-distance sizing, 3x effective leverage cap, actual funding, 0.05% taker fee and 0.02% slippage each side.
7. No fixed take profit. After twelve hours use completed-4h structure trailing; force exit after 48 hours.

There is no parameter grid, sensitivity variant, post-result symbol removal, or post-result direction removal.

## Honest evaluation boundary

- v1 development interval (`2025-12-15` to `2026-04-01`) is contaminated for v2 and inaccessible;
- sealed screen: `2026-04-01T00:00:00Z` to `2026-05-16T00:00:00Z`;
- inspected case interval (`2026-05-16` to `2026-07-16`) can never validate v2;
- prospective observation begins `2026-07-16T00:00:00Z` and matures once six completed trades are accumulated (no calendar-day waiting requirement).

The sealed screen requires six trades, including one RAVE and one LAB trade, positive ending equity, PF at least 1.25, drawdown no greater than 70%, at least 50% peak-profit retention, stopped-then-recovered no greater than 35%, and median winner capture at least 35%.

A screen pass creates only a prospective candidate, not a validated or paper-eligible strategy. Fewer than six trades is `insufficient_evidence`, not a pass. A gate failure rejects v2.

