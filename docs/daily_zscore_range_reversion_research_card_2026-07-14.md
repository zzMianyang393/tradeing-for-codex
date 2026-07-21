# Daily Z-Score Range Reversion: Research Card

- signal: completed UTC daily close has a trailing 20-day Z-score <= -2.5, using the prior 20 completed closes;
- direction: long at the next open plus a 4h availability delay;
- regime: completed 4h `震荡` label only;
- exit: first completed daily close at or above its 20-day mean, or 7 days; stop 2 ATR(14);
- cost: 0.16% round trip; one active event per symbol; no parameter sweep.

Formation is 2024 and OOS is 2025-01-01 to 2025-07-10. Each window requires >=15 compatible events, positive net mean, and <=25% positive-return concentration in any month. Research-only; never paper eligible.
