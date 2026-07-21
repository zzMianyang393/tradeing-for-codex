# Historical Fold Universe Audit

Date: 2026-07-13

A symbol is fold-eligible only when at least 98% of expected 15m bars exist.

## Fold Coverage

| Fold | Eligible Symbols |
| --- | ---: |
| 2024-H1 | 2 |
| 2024-H2 | 2 |
| 2025-H1 | 28 |
| 2025-H2 | 28 |
| 2026-H1 | 28 |

## Constant Universe

- symbols: 2
- list: `BTC-USDT-SWAP`, `ETH-USDT-SWAP`

## Research Contract

- new stability reports must show the constant full-window universe as the primary panel
- the fold-eligible expanding universe may be shown only as a secondary breadth panel
- fold returns must disclose universe changes
- this audit does not approve any strategy

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
