# Funding-Term Price Alignment Audit

Date: 2026-07-14

Frozen one-leg directional audit. This is not four-leg carry.

## Aggregate

- accepted positions: 151
- net return: +8.906947%
- maximum drawdown: 18.192100%
- win rate: 42.38%
- positive folds: 1/3
- top positive month share: 27.53%
- status: `observed_rejected`

## Direction Attribution

| Sleeve | Accepted | Return Contribution | Win |
| --- | ---: | ---: | ---: |
| `funding_term_price_alignment_v1_long` | 108 | -16.792592% | 37.04% |
| `funding_term_price_alignment_v1_short` | 43 | +25.699539% | 55.81% |

## Regime Attribution

- `low_volatility_drift_v2`: 29 accepted, -1.550455% contribution, 41.38% win
- `趋势上行`: 79 accepted, -15.242137% contribution, 35.44% win
- `趋势下行`: 43 accepted, +25.699539% contribution, 55.81% win

## Fold Returns

- `2025-H1`: +20.954851%
- `2025-H2`: -8.472427%
- `2026-H1`: -1.625997%

## Decision Reasons

- positive folds 1/3 < 2/3
- top positive month share 27.53% > 25%
- funding_term_price_alignment_v1_long return contribution -16.792592% <= 0%

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
