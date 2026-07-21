# 10U Persistent Event Trend 48h v2 — Sealed Screen Result

Formal status: `sealed_screen_insufficient_evidence`

The v2 contract `d20986a5c15aef78272f5b3d11ef200f57f110e1b714dc8115bb097ac98df116` was frozen before opening the `2026-04-01T00:00:00Z` through `2026-05-16T00:00:00Z` screen. The v1 development interval, the May–July inspected case interval, and prospective outcomes were not accessed.

## Result

| Metric | Result |
| --- | ---: |
| Persistence confirmations | RAVE 9 / LAB 11 / ETH 1 |
| Entry proposals | RAVE 7 / LAB 7 / ETH 1 |
| Executed trades / wins | 3 / 2 |
| Starting / ending equity | 10.0000 / 205.0062 USDT |
| Peak marked equity | 245.8109 USDT |
| Return | +1,950.06% |
| Profit factor | 6.4157 |
| Maximum marked drawdown | 18.7441% |
| Median winner capture | 81.75% |

The path was:

1. LAB long, `2026-04-06 12:00` to `2026-04-08 12:00` UTC: 10.00 → 18.12 USDT;
2. RAVE long, `2026-04-09 04:00` to `2026-04-11 04:00` UTC: 18.12 → 241.01 USDT;
3. LAB long hard stop, `2026-05-07 07:00` to `11:00` UTC: 241.01 → 205.01 USDT.

The RAVE trade entered near 0.3200 and exited near 1.9291 after 48 hours. Position notional was capped by stop-distance risk and 3x effective leverage; the result is not an unbounded-leverage artifact. The following LAB loss was approximately the frozen 15% equity risk budget after costs.

## Interpretation

Only three trades executed, below the pre-registered minimum of six. The screen therefore cannot pass regardless of its return. The result is also economically concentrated in one RAVE event. v2 remains unvalidated and ineligible for paper/live trading.

The screen supports one narrower claim: waiting for twelve hours of directional persistence can capture the kind of one-to-two-day move requested by the user. Repetition, not peak return, is now the unresolved question.

Authoritative evidence: `reports/ten_u_event_trend_screen_v2.json`.

