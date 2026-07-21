# Daily Williams %R Range Reversion Audit Result

## Frozen rule

- Rule: `daily_williams_r_range_reversion_v1`
- Universe: 28 eligible OKX perpetual symbols
- Context: completed 4h `震荡` label only
- Signal: daily Williams %R(14) <= -90 long, >= -10 short
- Entry: next daily open plus 4h delay
- Exit: %R crosses -50, 2 ATR(14) stop, or 7-day maximum holding period
- Friction: 0.16% round trip
- Formation: 2024-01-01 through 2024-12-31
- OOS: 2025-01-01 through 2025-07-10

## Result

| Split | Events | Net sum | Mean per event | Win rate | Positive-return month concentration |
| --- | ---: | ---: | ---: | ---: | ---: |
| Formation | 80 | -139.950737% | -1.749384% | 41.25% | 41.07% |
| OOS | 98 | -51.604228% | -0.526574% | 50.00% | 37.10% |

Status: `historical_rejected`.

The rule has sufficient event counts in both splits, but it fails both return and concentration gates in both samples. The frozen thresholds and exits were not tuned after seeing these results. It is not eligible as a standalone strategy or directional feature; any later reuse would require a separately registered, read-only semantic review rather than a parameter revision.

Safety gates remain closed: `approved_for_paper=[]`, `eligible_for_paper=false`, `safe_to_enable_trading=false`, and `ready_for_combo_backtest=false`.
