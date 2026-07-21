# Daily KAMA Trend: Research Card

- indicator: Kaufman Adaptive Moving Average using ER(10), fast=2, slow=30;
- trigger: completed daily close crosses above KAMA for long or below KAMA for short;
- regime: long only in completed 4h `趋势上行`, short only in `趋势下行`;
- entry: next daily open plus a 4h availability delay;
- exit: opposite KAMA cross or 10 days; hard stop 2 ATR(14);
- cost: 0.16% round trip; one active event per symbol; no parameter search.

Formation is 2024 and OOS is 2025-01-01 to 2025-07-10. Each window needs >=15 compatible events, positive net mean, and <=25% positive-return monthly concentration. Research-only; no paper eligibility.
