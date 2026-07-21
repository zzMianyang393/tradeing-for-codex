# Daily Spring/Upthrust Range Reversion Audit Result

Rule: `daily_spring_upthrust_range_reversion_v1`.

| Split | Events | Mean net return | Win rate | Positive-return month concentration |
| --- | ---: | ---: | ---: | ---: |
| Formation (2024) | 10 | -0.4381% | 40.0% | 67.1% |
| OOS (2025-01-01 to 2025-07-10) | 13 | -0.2260% | 30.8% | 90.1% |

The result is `insufficient_evidence`: both splits fail the 15-event floor.
It also fails the predeclared positive-mean and 25% concentration requirements.
The fixed 20-day channel, close-location thresholds, range-only label, delay,
holding horizon and friction assumption will not be retuned. The rule is
excluded from the directional combo pool and cannot enable trading.
