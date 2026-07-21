# Daily Regression Channel Trend: Research Card

- indicator: 30 completed daily closes fitted by ordinary least squares against time; residual standard deviation defines a 1.5-sigma channel;
- long trigger: completed close crosses above the upper channel while regression slope is positive;
- short trigger: completed close crosses below the lower channel while regression slope is negative;
- regime: long only in completed 4h `趋势上行`, short only in `趋势下行`;
- entry: next daily open plus a 4h availability delay;
- exit: completed close crosses the regression midline, or 10 days; hard stop 2 ATR(14);
- cost: 0.16% round trip; one active event per symbol; no regression window or channel-width sweep.

Formation is 2024 and OOS is 2025-01-01 to 2025-07-10. Both windows need >=15 compatible events, positive net mean, and <=25% positive-return monthly concentration. Research-only.
