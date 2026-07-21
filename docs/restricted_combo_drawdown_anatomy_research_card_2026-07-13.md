# Restricted Combo Drawdown Anatomy Research Card

Date: 2026-07-13

Status: frozen descriptive audit; no strategy parameters may change.

## Scope

Analyze the two post-hoc risk-adjusted combo watchlist pairs from the restricted shared-capital simulation. Rebuild the same events, costs, 10% position size, five-position account cap, and one-position-per-symbol rule.

## Maximum Drawdown Episode

For each pair record:

- prior equity peak date and value
- maximum drawdown trough date and value
- first recovery date, when available
- peak-to-trough and recovery duration
- pair drawdown compared with each standalone component

## Component Attribution

Accepted positions are marked on the same daily calendar. For each component calculate:

- cumulative marked-to-market PnL at the pair peak and trough
- PnL change during the pair drawdown window
- share of total negative component PnL
- average component exposure during the drawdown window
- negative days and jointly negative days

## Frozen Classification

- `common_failure`: both components lose during the pair drawdown and the smaller loss contributes at least 20% of total negative component PnL
- `minor_additive_loss`: both components lose, but the smaller loss contributes less than 20%
- `offsetting_component`: one component gains or remains flat while the other loses

This classification is descriptive. It cannot override the failed pre-registered absolute drawdown gate.

## Safety

- observed data stops at 2026-07-10
- no prospective signal or return may be read
- no allocation, filter, or entry rule may be optimized from this audit
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`
