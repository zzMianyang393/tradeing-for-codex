# Stage 4 Data Sources Acceptance

Stage 4 expands research inputs beyond OHLCV K lines. The first implemented
source is OKX funding-rate history.

## Implemented

- `funding_rate.py` defines a `FundingRate` data model.
- OKX funding history rows can be parsed into stable local records.
- Funding rates can be saved to and loaded from CSV cache files.
- `funding_rate.py --symbols ... --days ... --out ...` downloads funding-rate
  history with CSV merge/resume behavior and transient error retries.
- `add_funding_features` returns `FundingFeatureBar` values that preserve all
  existing `FeatureBar` fields and add:
  - `funding_rate`
  - `funding_realized_rate`
  - `funding_rate_ma`
- `load_market(..., include_funding=True)` attaches cached funding-rate
  features when a matching `<symbol>_funding.csv` file exists.
- `funding_signal_for` provides an optional, default-off funding-rate strategy
  signal for extreme funding-rate conditions.

## Current Limits

- Funding strategy is available but remains disabled in the default profile
  until it passes rolling-window validation.

## Next Step

- Add trades, order book, and open interest data sources.
- Run funding-module rolling-window validation before enabling it by default.
