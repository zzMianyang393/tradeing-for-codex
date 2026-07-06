# Stage 4 Data Sources Acceptance

Stage 4 expands research inputs beyond OHLCV K lines. The first implemented
sources are OKX funding-rate history, open-interest history, and trade flow.

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
- `open_interest.py` defines an `OpenInterest` data model.
- OKX open-interest history rows can be parsed into stable local records.
- Open interest can be saved to and loaded from CSV cache files.
- `open_interest.py --symbols ... --days ... --out ...` downloads
  open-interest history with CSV merge behavior.
- `add_open_interest_features` returns `OpenInterestFeatureBar` values that
  preserve all existing `FeatureBar` fields and add:
  - `open_interest`
  - `open_interest_currency`
  - `open_interest_change_pct`
  - `open_interest_ma`
- `load_market(..., include_open_interest=True)` attaches cached open-interest
  features when a matching `<symbol>_open_interest.csv` file exists.
- `trade_flow.py` defines a `TradeTick` data model.
- OKX historical trade rows can be parsed into stable local records with
  active buy/sell side and quote volume.
- Trade ticks can be saved to and loaded from CSV cache files.
- `trade_flow.py --symbols ... --out ...` downloads historical trade rows with
  CSV merge behavior.
- `add_trade_flow_features` returns `TradeFlowFeatureBar` values that preserve
  all existing `FeatureBar` fields and add:
  - `active_buy_quote`
  - `active_sell_quote`
  - `active_buy_ratio`
  - `trade_flow_imbalance`
- `load_market(..., include_trade_flow=True)` attaches cached trade-flow
  features when a matching `<symbol>_trades.csv` file exists.

## Current Limits

- Funding strategy is available but remains disabled in the default profile
  until it passes rolling-window validation.
- Open-interest features are not consumed by a strategy yet.
- Trade-flow features are not consumed by a strategy yet.

## Next Step

- Add order book data source.
- Add an open-interest strategy/filter and validate it independently.
- Add a trade-flow strategy/filter and validate it independently.
- Run funding-module rolling-window validation before enabling it by default.
