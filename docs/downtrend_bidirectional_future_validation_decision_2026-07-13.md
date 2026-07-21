# Downtrend Bidirectional Future Validation Decision

Date: 2026-07-13

## Decision

The exact fixed-budget combination is rejected after its locked future-window
validation. This rejects the tested construction, not the broader weak-strategy
portfolio thesis.

## Locked Result

- window: `2025-07-11` to `2026-07-10`
- data-eligible universe: 28 symbols; SEI excluded before performance was known
- candidate events: 344
- accepted positions: 86
- net return: `+0.039957%`
- maximum drawdown: `30.118000%`
- realized win rate: `47.6744%`
- top positive month share: `31.4064%`

The combination failed three pre-registered requirements: drawdown exceeded 20%,
the RSI component contribution was negative, and monthly concentration exceeded
25%.

## Component Decision

### RSI rebound long

- 44 accepted positions
- return contribution: `-10.216043%`
- win rate: `47.7273%`
- decision: remove from the directional candidate pool for the next combination
- allowed future role: context label or risk-warning input only

This role change follows a real future failure. The same downtrend-long rule must
not be reintroduced under a new name or with a small threshold adjustment.

### EMA continuation short

- 42 accepted positions
- return contribution: `+10.256000%`
- win rate: `47.6190%`
- top positive month concentration: `43.1606%`
- decision: retain as a conditional weak-signal candidate with a concentration
  warning; do not approve it as a strategy or paper-trading component

## Drawdown Evidence

- peak: `2025-10-11`, equity `139,964.052886`
- trough: `2026-06-10`, equity `97,809.669253`
- duration: 242 days
- average long exposure: `24.6048%`
- average short exposure: `11.4211%`
- drawdown-period realized PnL:
  - EMA short: `+12,108.890408` USDT
  - RSI long: `-20,156.444260` USDT

The portfolio was not balanced through the drawdown. It remained net long on 136
days, net short on 41 days, and approximately neutral on 66 days.

## Next Research Program

1. Preserve the EMA downtrend-short component without parameter changes.
2. Develop independent uptrend and range-regime components from the prototype
   universe using rolling historical research windows.
3. Build a deterministic regime router that activates only components declared
   compatible with the last completed label; do not use machine learning yet.
4. Enforce separate capital budgets by regime and component before evaluating
   aggregate returns.
5. Treat all data through `2026-07-10` as observed research data from now on.
6. Reserve data from `2026-07-11` forward for the next frozen design. Interim
   90-day checks are diagnostic only; a 365-day prospective window remains the
   approval-grade target.

No parameter search may use the failed future result. A replacement construction
must be pre-registered before its reserved prospective data are evaluated.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

