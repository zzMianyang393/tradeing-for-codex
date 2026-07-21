# 10U Single-Symbol Event Trend 48h v1 — Formation Result

Formal status: `formation_fail`

The primary frozen contract `6653b5f4aa376f94d679dae1a8137ba823d352ac571d5075fe917d3f3516304a` was evaluated only on `2025-12-15T16:00:00Z` through `2026-04-01T00:00:00Z`. Retrospective validation, the inspected May–July case window, and prospective OOS were not accessed.

## Account result

| Metric | Result |
| --- | ---: |
| Trades / wins | 20 / 7 |
| Starting / ending equity | 10.0000 / 7.5839 USDT |
| Peak equity | 15.0491 USDT |
| Return | -24.1612% |
| Profit factor | 0.7676 |
| Maximum marked drawdown | 49.6058% |
| Fees / slippage / funding | 0.4904 / 0.1962 / -0.3061 USDT |
| Median winner capture | 40.96% |
| Stopped then recovered 1R | 37.50% |

The gate failed profit factor, ending equity, peak-profit retention, and stopped-then-recovered requirements. Both frozen sensitivity diagnostics also failed and are forbidden from rescuing the primary.

## Failure attribution

- ETH produced +2.6545 USDT, LAB -3.9331 USDT, and RAVE -1.1375 USDT. These observed contributions cannot justify a post-hoc ETH-only universe.
- Long trades produced -3.6395 USDT and shorts +1.2234 USDT. This cannot justify a post-hoc short-only rule.
- The two positions that reached the 48-hour time exit both won and produced +4.8145 USDT. Five hard-stop exits lost -4.7060 USDT; three structural close invalidations lost -2.3371 USDT.
- All 52 four-hour ignition events were inspected without a threshold grid. Directional continuation was positive for 51.92% after 4h, 42.31% after 24h, and only 38.46% after 48h. Median 48h directional return was -2.61%.

The primary failure is therefore upstream of stop placement: a single four-hour range/volume expansion bar does not reliably identify the direction of the following one-to-two-day move. Wider stops would increase exposure to a direction hypothesis that is usually wrong by 48 hours.

## Decision

v1 is permanently rejected at Formation. Validation and OOS remain locked. Its Formation interval is now development-contaminated for any successor. A successor may reuse the broad event-trend objective only if it has a separately fingerprinted direction-confirmation state machine and uses a different sealed evaluation interval.

Authoritative evidence:

- `reports/ten_u_event_trend_formation_v1.json`
- `reports/ten_u_event_trend_postmortem_v1.json`
- `reports/ten_u_event_trend_preregistration_v1.json`

