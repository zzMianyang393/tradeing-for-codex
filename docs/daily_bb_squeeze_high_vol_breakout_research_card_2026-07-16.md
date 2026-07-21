# Daily Bollinger Squeeze High-Volatility Breakout Research Card

Rule ID: `daily_bb_squeeze_high_vol_breakout_v1`.

Use completed daily Bollinger Bands `20/2`. A signal requires current band
width to be at or below the 20th percentile of the prior 120 completed daily
widths, then a completed close outside the upper band (long) or lower band
(short). It is valid only when the completed four-hour label at the signal is
`高波动转换`. Enter four hours later; exit on a close back through the daily
middle band, a `2 x ATR(14)` stop, or after ten days. Round-trip friction is
0.16%.

Formation is 2024 and OOS is 2025-01-01 through 2025-07-10. Both windows need
at least 15 events, positive mean net return and no month above 25% of positive
return. No post-result changes to parameters, regime, symbols, direction or
holding horizon are permitted. This is research-only and cannot enable paper
or live trading.
