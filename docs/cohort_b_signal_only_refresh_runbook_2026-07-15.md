# Cohort B Signal-Only Refresh

`cohort_b_signal_only_refresh.py` rebuilds the RSI and volatility-expansion staging sources from the current local data, combines them, and invokes the existing append-only pipeline with `commit=False` only.

It does not download market data, import `runner.py`, expose a commit flag, or publish observations. A nonzero staging signal is still only a dry-run finding; a separately reviewed publication decision remains required.

The report `reports/cohort_b_signal_only_refresh.json` records source cutoffs, source counts, append validation, decision, and closed safety gates. It contains no price, return, PnL, order, or position fields.
