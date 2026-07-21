# Weekend Low-Liquidity Reversion: Research Card

Status: `eligible_for_research`, not a trading candidate.

- data: completed UTC daily OHLCV, single perpetual market only;
- timing: evaluate only the completed Saturday UTC daily bar; no Sunday/Monday re-entry;
- liquidity condition: Saturday quote volume is below the trailing 20-day 30th percentile;
- price condition: Saturday close is below its 5-day EMA and daily RSI(14) is below 40;
- direction: long at the following Sunday UTC daily open;
- compatible regime: `震荡` only, from the last completed 4h label;
- exit: first close at or above EMA5, or 2 days; hard stop 1.5 ATR(14);
- friction: 0.16% round trip; no funding, OI, external calendar, grid, or averaging input.

Historical contract: formation `2024-01-01` to `2024-12-31`; OOS `2025-01-01` to `2025-07-10`; >=15 compatible events per window, positive net mean per window, and <=25% positive-return contribution from any month. No weekday or threshold sweep.

Only a signal-only generator may be built after this audit; paper eligibility remains false.
