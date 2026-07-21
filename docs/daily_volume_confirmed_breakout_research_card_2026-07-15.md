# Daily Volume Confirmed Breakout: Research Card

- Rule: `daily_volume_confirmed_breakout_v1`.
- Signal: completed daily close outside the preceding 20-day channel and daily quote volume at least 2.5 times the preceding completed 5-day mean.
- Context: long only in completed 4h `趋势上行`; short only in completed 4h `趋势下行`.
- Entry: next daily open plus 4h availability delay.
- Exit: 2 ATR(14) hard stop or 10 calendar days.
- Cost: 0.16% round trip.
- Samples: formation 2024; OOS 2025-01-01 through 2025-07-10.
- Gates per split: at least 15 events, positive net mean, and positive-return month concentration no greater than 25%.

No parameter sweep, post-result threshold adjustment, paper approval, combination approval, or runner integration is permitted.
