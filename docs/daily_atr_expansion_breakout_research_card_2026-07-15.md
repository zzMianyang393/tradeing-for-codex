# Daily ATR Expansion Breakout: Research Card

- Rule: `daily_atr_expansion_breakout_v1`.
- Signal: daily close beyond the prior 20 completed daily highs (long) or lows (short), with the signal day's high-low range at least 1.5 times the completed ATR(14).
- Context: long only in completed 4h `趋势上行`; short only in completed 4h `趋势下行`.
- Entry: next daily open plus 4h availability delay.
- Exit: 2 ATR(14) hard stop or 10 calendar days.
- Cost: 0.16% round trip.
- Samples: formation 2024; OOS 2025-01-01 through 2025-07-10.
- Gates per split: at least 15 events, positive net mean, and positive-return month concentration no greater than 25%.

This is a single frozen baseline. It may not be tuned after the audit and cannot be connected to a combination, paper trading, or `runner.py` without a separate approval process.
