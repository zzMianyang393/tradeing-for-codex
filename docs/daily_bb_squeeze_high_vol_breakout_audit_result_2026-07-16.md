# Daily Bollinger Squeeze High-Volatility Breakout Audit Result

Rule: `daily_bb_squeeze_high_vol_breakout_v1`.

| Split | Events | Mean net return | Win rate | Positive-return month concentration |
| --- | ---: | ---: | ---: | ---: |
| Formation (2024) | 1 | +9.7336% | 100.0% | 100.0% |
| OOS (2025-01-01 to 2025-07-10) | 11 | -1.4490% | 27.3% | 50.7% |

The rule is `insufficient_evidence`: neither split meets the 15-event floor;
OOS is also negative and overly concentrated. Its frozen daily Bollinger,
width-percentile, high-volatility regime, delay, stop and holding rules are
not adjusted. It is excluded from the directional combo pool and cannot enable
paper or live trading.
