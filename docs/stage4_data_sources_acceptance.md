# Stage 4 Data Sources Acceptance

Stage 4 expands research inputs beyond OHLCV K lines. The first implemented
sources are OKX funding-rate history, open-interest history, trade flow, and
order-book snapshots.

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
- `trade_flow.py --pages ...` can walk older historical trade pages by using
  the oldest returned trade id as the next `before` cursor.
- `add_trade_flow_features` returns `TradeFlowFeatureBar` values that preserve
  all existing `FeatureBar` fields and add:
  - `active_buy_quote`
  - `active_sell_quote`
  - `active_buy_ratio`
  - `trade_flow_imbalance`
- `load_market(..., include_trade_flow=True)` attaches cached trade-flow
  features when a matching `<symbol>_trades.csv` file exists.
- `trade_flow_signal_for` provides an optional, default-off strategy signal for
  buy/sell trade-flow imbalance breakouts and breakdowns.
- `order_book.py` defines an `OrderBookSnapshot` data model.
- OKX order-book snapshots can be parsed into stable local records with
  spread, quote-depth, and depth-imbalance fields.
- Order-book snapshots can be saved to and loaded from CSV cache files.
- `order_book.py --symbols ... --out ...` appends current order-book snapshots
  with CSV merge behavior by timestamp.
- `add_order_book_features` returns `OrderBookFeatureBar` values that preserve
  all existing `FeatureBar` fields and add:
  - `best_bid`
  - `best_ask`
  - `order_book_spread_pct`
  - `bid_depth_quote`
  - `ask_depth_quote`
  - `depth_imbalance`
- `load_market(..., include_order_book=True)` attaches cached order-book
  features when a matching `<symbol>_order_book.csv` file exists.
- `RiskManager` can reject new orders when cached order-book spread is too wide
  or directional quote depth is too thin via:
  - `rm_max_order_book_spread_pct`
  - `rm_min_order_book_depth_quote`
- `open_interest_signal_for` provides an optional, default-off strategy signal
  for rising-open-interest breakouts and breakdowns.

## Current Limits

- Funding strategy is available but remains disabled in the default profile
  until it passes rolling-window validation.
- Open-interest strategy is available but remains disabled in the default
  profile until it passes rolling-window validation.
- Trade-flow strategy is available but remains disabled in the default profile
  until it passes rolling-window validation.
- Order-book features are consumed by RiskManager only when the new limits are
  explicitly configured.
- Optional funding, open-interest, trade-flow, and order-book caches have been
  downloaded for all 29 discovered symbols in the local `data` folder.
- Module rolling audits with `--max-windows 4` have been run for funding,
  open-interest, trade-flow, and order-book data. They remain below target, so
  none of these optional modules should be enabled by default yet.
- Rolling audit reports now include reason-level aggregation. The current
  reports do not show accepted module-specific trade reasons under the present
  thresholds and cache depth.
- Current optional caches are still shallow for rolling validation: funding is
  recent history, open-interest is one recent OKX page, trade-flow now has
  paginated recent ticks, and order-book is point-in-time snapshots.

## Next Step

- Extend optional cache depth where the exchange API supports pagination, then
  rerun full rolling validation.
- Tune module signal thresholds only after deeper cache coverage confirms that
  the missing module-specific reasons are not caused by data sparsity.
- Validate order-book liquidity/spread limits in simulated execution before
  setting defaults.
