# Stage 4 Data Sources Acceptance

Stage 4 expands research inputs beyond OHLCV K lines. The first implemented
source is OKX funding-rate history.

## Implemented

- `funding_rate.py` defines a `FundingRate` data model.
- OKX funding history rows can be parsed into stable local records.
- Funding rates can be saved to and loaded from CSV cache files.
- `add_funding_features` returns `FundingFeatureBar` values that preserve all
  existing `FeatureBar` fields and add:
  - `funding_rate`
  - `funding_realized_rate`
  - `funding_rate_ma`

## Current Limits

- The module exposes page-level OKX fetching, but there is not yet a full
  multi-day downloader CLI with resume/retry behavior.
- Funding features are not yet connected to `load_market`.
- No strategy consumes funding features yet.

## Next Step

- Add a resumable funding-rate downloader command.
- Wire optional funding feature loading into market construction.
- Add an independent funding-rate strategy signal and backtest report.
