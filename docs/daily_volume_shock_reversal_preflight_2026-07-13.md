# Daily Volume-Shock Reversal Preflight

Date: 2026-07-13

Event inventory only. No forward returns or trade outcomes are computed.

## Coverage

| Panel | Events | Long | Short | Folds With Events | Folds >=10 | Top Month Share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| constant BTC/ETH | 8 | 2 | 6 | 4/5 | 0/5 | 25.00% |
| fold-eligible expanding | 168 | 66 | 102 | 5/5 | 3/5 | 14.88% |

## Fold Counts

| Panel | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| constant BTC/ETH | 1 | 2 | 3 | 0 | 2 |
| fold-eligible expanding | 1 | 2 | 63 | 37 | 65 |

## Decision

- primary events 8 < 15

Status: `event_coverage_blocked`.

## Safety

- forward-return fields present: `false`
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
