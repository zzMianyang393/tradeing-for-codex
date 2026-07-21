# Parkinson Volatility Extreme Reversion: Research Card

Status: `eligible_for_research`, not a trading candidate.

- data: completed UTC daily OHLCV, single perpetual market only;
- volatility: 20-day Parkinson estimator, ranked against its trailing 120 completed daily observations;
- trigger: volatility percentile >= 90, using the nearest-rank 90th percentile of the trailing 120 completed observations, and the completed daily close is below its 20-day EMA;
- direction: long at the next UTC daily open;
- compatible regime: `高波动转换` only, using the last completed 4h label available at that open;
- exit: first completed daily close at or above EMA20, or 7 days; hard stop 2 ATR(20);
- friction: 0.16% round trip; no scale-in, hedge, grid, or leverage adjustment.

Historical contract: formation `2024-01-01` to `2024-12-31`; OOS `2025-01-01` to `2025-07-10`; >=15 compatible events in each window, positive net mean in both, and <=25% positive-return contribution from 2024-11. No parameter sweep.

Only a signal-only generator may be built after this audit; paper eligibility remains false.
