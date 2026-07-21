# Daily Williams %R Range Reversion: Research Card

Frozen rule: Williams %R(14) on completed UTC daily bars. In a completed-4h `震荡` regime, %R <= -90 emits a long observation and %R >= -10 emits a short observation. Entry is delayed four hours from the next daily open. Exit is the first completed daily %R return through -50, a 2 ATR(14) stop, or seven days. Round-trip friction is 0.16%.

Formation: 2024-01-01 to 2024-12-31. OOS: 2025-01-01 to 2025-07-10. Each split requires at least 15 events, positive net mean, and no positive-return month contribution above 25%. No parameter grid or post-result change is permitted.

This is research-only. If it clears the historical screen, it must undergo a semantic-overlap audit against the existing RSI range/reversion features before any future observation or combination work.
