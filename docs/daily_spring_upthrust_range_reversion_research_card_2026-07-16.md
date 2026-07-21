# Daily Spring/Upthrust Range Reversion Research Card

Rule ID: `daily_spring_upthrust_range_reversion_v1`.

On a completed daily bar, use the prior 20 completed daily bars as the
channel. In a completed `震荡` regime only, go long when price breaks below the
prior channel low but closes back above it, with close location at least 0.60.
Go short symmetrically after an upside break closes back inside, with close
location at most 0.40. Enter four hours later. Exit on a return to the
opposite channel boundary, a `2 x ATR(14)` stop, or five days. Friction is
0.16% round trip.

Formation and OOS windows are fixed to 2024 and 2025-01-01 to 2025-07-10.
Both require 15 events, positive net mean, and at most 25% positive-return
concentration in any month. No parameter, symbol, direction, or regime change
is allowed after inspection. This is research-only and cannot enable trading.
