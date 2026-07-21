# Daily RSI Percentile Range Reversion: Research Card

- signal: completed daily RSI(14) is at or below the nearest-rank 5th percentile of its prior 120 completed RSI observations;
- direction: long at the next open plus a 4h availability delay;
- regime: completed 4h `震荡` only;
- exit: first completed daily RSI(14) >= 50, or 7 days; stop 2 ATR(14);
- cost: 0.16% round trip; no threshold, window, regime, or holding-period search.

Formation is 2024, OOS is 2025-01-01 to 2025-07-10. Each window requires >=15 events, positive net mean, and <=25% positive-return concentration. Research-only.
