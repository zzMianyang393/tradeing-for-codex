# Daily KDJ Range Reversion Research Card

Rule ID: `daily_kdj_range_reversion_v1`.

The only permitted entry is a completed daily KDJ `9/3/3` bullish crossover
with `K < 20`, while the entry timestamp is labelled `震荡` by the completed
four-hour regime labeler. Enter four hours after the completed daily signal.
Exit at `K >= 80`, a `2 x ATR(14)` stop, or seven days, whichever occurs first.
Use a 0.16% round-trip friction assumption and a 15-minute cooldown after exit.

Formation is 2024-01-01 through 2024-12-31. OOS is 2025-01-01 through
2025-07-10. Both splits require at least 15 events, positive mean net return,
and no positive-return month above 25% contribution. Parameters, symbols,
holding horizon, direction and regime restriction are frozen after this card.

This audit is research-only. It cannot approve standalone, paper, or live
trading. A passing outcome could only become a directional weak-feature
candidate after separate feature-pool preflight.
