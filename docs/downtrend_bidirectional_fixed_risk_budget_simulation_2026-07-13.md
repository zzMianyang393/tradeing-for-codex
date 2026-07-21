# Downtrend Bidirectional Fixed Risk Budget

Date: 2026-07-13

Post-hoc diagnostic overlay: maximum two RSI long positions and three EMA short positions. Unused slots remain cash.

## Results

| Window | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Month Concentration | Return Delta | DD Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `formation` | 26 | 43 | +4.749591% | 7.363900% | 53.85% | 13.65% | 29.84% | -10.620598% | -7.058500% |
| `formation_excluding_2024_11` | 24 | 33 | +1.027201% | 7.363900% | 50.00% | 12.33% | 36.95% | -0.649956% | -7.058500% |
| `oos` | 38 | 128 | +24.191096% | 10.937500% | 60.53% | 26.10% | 24.62% | +17.453908% | -25.628200% |

## OOS Component Attribution

| Component | Accepted | Rejected | Return Contribution | Win |
| --- | ---: | ---: | ---: | ---: |
| `ema_continuation_short` | 13 | 11 | +4.626490% | 61.54% |
| `rsi_rebound_long` | 25 | 117 | +19.564606% | 60.00% |

## Decision

- Current diagnostic thresholds pass, but this overlay is not validated because it was designed after observing OOS drawdown.

Validation status: `posthoc_overlay_requires_future_unseen_window`.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
