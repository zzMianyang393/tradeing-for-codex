# Daily Parabolic SAR Trend: Research Card

- Rule: `daily_parabolic_sar_trend_v1`.
- Signal: completed daily Parabolic SAR direction flip, using AF step 0.02 and AF cap 0.20.
- Context: long only under completed 4h `趋势上行`; short only under completed 4h `趋势下行`.
- Entry: next daily open plus 4h availability delay.
- Exit: opposite SAR flip, 2 ATR(14) hard stop, or 10 calendar days.
- Cost: 0.16% round trip.
- Samples: formation 2024; OOS 2025-01-01 through 2025-07-10.
- Gates for each split: at least 15 events, positive net mean, and positive-return month concentration no greater than 25%.

This is a single frozen baseline. No parameter sweep, post-result tuning, standalone paper approval, or runner integration is allowed. A pass only permits separate overlap and prospective-observation review.
