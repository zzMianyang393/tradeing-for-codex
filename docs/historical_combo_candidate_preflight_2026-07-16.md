# Historical Combo Candidate Preflight

## Purpose

This is the first historical-combination gate. It judges frozen weak factors
only after their events have been filtered to the regimes declared compatible
before evaluation. It is not a standalone-strategy retry and it is not a
portfolio backtest.

## Frozen requirements

- At least 30 regime-compatible historical events.
- At least 12 active calendar months.
- A factor above 25% positive-return concentration may enter a *historical
  combo hypothesis only* with an explicit concentration penalty and capped
  contribution. It remains ineligible as a standalone strategy.
- A factor marked as a post-hoc semantic repair requires independent future
  OOS confirmation and cannot enter a historical combo hypothesis yet.
- At least three eligible directional factors are required before specifying a
  combo hypothesis.

## Boundaries

All factors remain non-standalone and ineligible for paper trading. Context
labels and risk filters remain descriptive or veto-only; they cannot be
reclassified as directional alpha here. Grid, martingale, invalid, data-blocked
and hard-cost-blocked families remain excluded.

The output is an audit report, not a weighting scheme. A passing result only
allows a subsequent frozen historical hypothesis specification; it does not
permit a combo backtest, paper trading, or execution.
