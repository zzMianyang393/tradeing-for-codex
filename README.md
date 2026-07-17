# Tradering

`tradering` is a self-contained crypto perpetual backtesting and signal research program.

**Requires Python ≥ 3.10** (uses `dataclass(slots=True)`).

## Production track (start here if you want paper trading)

Daily path is **`prod/`** — not the hundreds of research audit scripts.

| Goal | Command |
|------|---------|
| Admit 10U high-risk sleeve to paper-prep | `python -m prod.cli admit-ten-u --accept-concentration-risk` |
| Run one local paper cycle | `python -m prod.cli paper-cycle` |
| Status | `python -m prod.cli status` |

- Prospective sealed waiting is **not** required for paper-prep.
- Live trading stays closed until a separate promotion step.
- Details: [`docs/PRODUCTION_TRACK.md`](docs/PRODUCTION_TRACK.md)
- GitHub slim notes: [`docs/REPO_SLIM_GITHUB.md`](docs/REPO_SLIM_GITHUB.md)

It uses local OKX 1m CSV data when available, resamples it to 15m bars, then runs a multi-symbol,
multi-regime strategy from a configurable starting balance.

## What it does

- Selects tradable symbols from the local data folder by liquidity, volatility, trend quality, and spread proxy.
- Handles uptrend, downtrend, and range regimes with different entry/exit logic.
- Sizes every trade from account equity, ATR stop distance, leverage caps, and portfolio exposure limits.
- Includes fees, slippage, stop loss, take profit, time stop, and trailing exit.
- Produces validation reports and overfit/rolling-window audit reports for the configured target windows.
- Marks unavailable windows when the selected symbol pool does not have enough overlapping data.
- Can download more OKX history with the included downloader.

This is research software, not a profit guarantee. It is intentionally built to report weak periods instead of hiding them.

## Quick start

```bash
cd E:\ai-trade\tradering
python run.py --report reports\quantify_latest.json
```

The default data path is `data`, which is included in this repository.
To run another local dataset, pass `--data <path>`.

## Dry-run execution runner

The dry-run runner is the first simulated-execution layer. It uses local SQLite
state and the in-process `DryRunExchange`; it does not connect to OKX or place
real orders.

```bash
python runner.py --once --db reports\dry_run_state.db --equity 25
python runner.py --status --db reports\dry_run_state.db
python runner.py --reconcile --db reports\dry_run_state.db
python runner.py --loop --iterations 3 --interval 0 --db reports\dry_run_state.db --equity 25
```

To verify OKX simulated-trading connectivity without placing orders, set read
only simulated API credentials and run:

```bash
set OKX_API_KEY=your_key
set OKX_API_SECRET=your_secret
set OKX_API_PASSPHRASE=your_passphrase
python runner.py --okx-check --okx-symbol BTC-USDT-SWAP
python runner.py --reconcile --exchange okx --db reports\dry_run_state.db
python runner.py --okx-smoke-order --confirm-okx-smoke-order --okx-symbol BTC-USDT-SWAP --okx-smoke-direction long --okx-smoke-qty 0.001 --okx-smoke-price 1 --okx-smoke-notional 1 --okx-smoke-margin 1
python runner.py --okx-submit-signal --confirm-okx-submit-signal --db reports\dry_run_state.db --okx-symbol BTC-USDT-SWAP --okx-signal-direction long --okx-signal-price 50000 --okx-signal-notional 10 --okx-signal-margin 1 --okx-signal-leverage 10
python runner.py --okx-sync-orders --db reports\dry_run_state.db
python runner.py --okx-close-position --confirm-okx-close-position --db reports\dry_run_state.db --position-id <local_position_id> --okx-close-price 50100
python runner.py --okx-snapshot --db reports\dry_run_state.db
python runner.py --okx-monitor-loop --iterations 3 --interval 5 --db reports\dry_run_state.db
python runner.py --okx-health-report --db reports\dry_run_state.db --stale-order-minutes 30
```

Current runner scope:

- `--once` performs one dry-run cycle, writes an account snapshot, manages local
  open positions, executes provided in-process signal requests, and reconciles
  state.
- `--status` prints the latest local account snapshot, open positions, and trade
  summary as JSON.
- `--reconcile` compares local SQLite positions with the dry-run exchange state.
- `--reconcile --exchange okx` compares local SQLite positions with OKX
  simulated-account positions.
- `--loop` repeats empty dry-run cycles for a finite number of iterations.
- `--okx-check` reads OKX simulated account balance, ticker, and positions via
  the sandbox header; it is read-only and does not submit orders.
- `--okx-smoke-order` places one OKX simulated limit order and immediately
  requests cancellation. It requires `--confirm-okx-smoke-order` and runs the
  RiskManager before submitting.
- `--okx-submit-signal` submits one manual signal to OKX simulated trading
  after local/exchange position reconciliation and RiskManager approval. It
  writes the order result into SQLite and requires `--confirm-okx-submit-signal`.
- `--okx-sync-orders` refreshes local live/pending OKX simulated orders by
  exchange order id. Filled orders are converted into local open positions.
- `--okx-close-position` submits a simulated close order for an existing local
  open position after local/exchange reconciliation. A later `--okx-sync-orders`
  run turns a filled close order into a closed position and trade record.
- `--okx-snapshot` writes a read-only OKX simulated runtime snapshot into
  SQLite account history and prints account, pending-order, position, and trade
  summary metrics as JSON.
- `--okx-monitor-loop` runs a finite monitor loop that syncs OKX simulated
  orders and then writes a runtime snapshot each cycle.
- `--okx-health-report` prints a machine-readable health report. It flags OKX
  API failures, local/exchange position drift, stale active orders, and risk
  pauses as `ok`, `warning`, or `critical`. Use `--stale-order-minutes` to
  tune stale active-order detection.

## Download more data

```bash
cd E:\ai-trade\tradering
python okx_downloader.py --symbols BTC-USDT-SWAP ETH-USDT-SWAP SOL-USDT-SWAP --days 365 --bar 15m --out data
python funding_rate.py --symbols BTC-USDT-SWAP ETH-USDT-SWAP --days 90 --out data
python open_interest.py --symbols BTC-USDT-SWAP ETH-USDT-SWAP --days 30 --out data --period 15m
python trade_flow.py --symbols BTC-USDT-SWAP ETH-USDT-SWAP --out data --pages 10
python order_book.py --symbols BTC-USDT-SWAP ETH-USDT-SWAP --out data --depth 20
```

The downloader writes files in the same format as the existing local CSVs.
Funding-rate support is available in `funding_rate.py` for OKX funding history
parsing, CSV caching, and attaching funding fields to `FeatureBar` streams for
future strategy signals. Use `load_market(data_dir, timeframe, include_funding=True)`
to attach cached funding features during market construction.
Open-interest support is available in `open_interest.py`; use
`load_market(data_dir, timeframe, include_open_interest=True)` to attach cached
open-interest fields.
Trade-flow support is available in `trade_flow.py`; use
`load_market(data_dir, timeframe, include_trade_flow=True)` to attach cached
active buy/sell quote-volume fields.
Order-book snapshot support is available in `order_book.py`; use
`load_market(data_dir, timeframe, include_order_book=True)` to attach cached
spread/depth/imbalance fields.

## Dashboard

Render a local HTML dashboard from the SQLite trading state:

```bash
python dashboard.py --db reports\dry_run_state.db --out reports\dashboard.html
python dashboard.py --serve --db reports\dry_run_state.db --host 127.0.0.1 --port 8090
```

Open `reports\dashboard.html` in a browser to review account snapshots, open
positions, recent trades, risk events, and health alerts. The page includes a
local equity curve, view switching, and table filtering without requiring a
server. The optional local server renders the same dashboard at `/` and exposes
the latest dashboard payload at `/api/dashboard`.

## Outputs

- `reports/latest.json`: machine-readable full report.
- `reports/overfit_audit_summary.json`: compares the current window-specific profile with same-config control cases.
- `reports/rolling_window_audit.json`: tests repeated historical slices instead of only the latest endpoint.
- `reports/consistency_search.json`: ranks candidate configs by rolling-window consistency.
- Console summary: period PnL, win rate, drawdown, trade count, and symbol breakdown.

## Notes

- The included `data` folder contains the downloaded local research dataset used by the latest reports.
- The current default profile is a research profile, not a proven robust production profile.
- No strategy in this repository is currently approved for simulated or live trading.
- Long-term development should follow `docs/development_roadmap.md`: mature the project through data expansion, strategy portfolios, anti-overfit validation, risk management, simulated execution, and monitoring.
- Allowed symbols: all loaded symbols; the program dynamically selects the top symbols each window.
- Enabled regimes: `transition`, `range`, with a low-risk adaptive downtrend module.
- Target gates: 365/180/90/60/30/14/7 day return floors plus win rate >= 66%.
- Risk controls include profit locking after equity growth and faster range exits while equity is in defense mode.
- The default profile disables the old 365 day aggressive profile and transition long entries.
- Selector quality gates filter low-liquidity and high-noise symbols before ranking candidates.

## Candidate validation

Historical validation numbers in older reports are not current performance
claims. Several earlier candidate scripts counted their own conditions but
executed the legacy router, so their results are invalid as independent strategy
evidence. Use the following validator instead; it runs each candidate's actual
entry signal through the common cost, sizing, exit and risk engine and records a
trade fingerprint for integrity checks.

```bash
python unified_validation.py --strategy intraday_reversal --windows 90 --universes majors --out reports\candidate_smoke.json
python unified_validation.py --strategy all --out reports\unified_validation.json
```

The first command is the recommended smoke test. Run the full matrix only after
the individual candidate result is understood. A result is research evidence,
not a trading approval; it must remain positive across isolated periods,
universes and stressed costs before any simulated-execution work resumes.

Optional data-source modules can be validated independently before they are
enabled in the default profile:

```bash
python rolling_window_audit.py --module funding --out reports\rolling_funding_audit.json
python rolling_window_audit.py --module open-interest --out reports\rolling_open_interest_audit.json
python rolling_window_audit.py --module trade-flow --out reports\rolling_trade_flow_audit.json
python rolling_window_audit.py --module order-book --out reports\rolling_order_book_audit.json
```

Each rolling audit report includes `data_source_coverage`, which shows whether
the local `data` folder actually contains the optional cache files required by
that module.

Run the consolidated anti-overfit validation pipeline:

```bash
python full_validation.py --out reports\full_validation.json
```

This combines latest-window validation, walk-forward, parameter sensitivity,
Monte Carlo reshuffling, single-trade contribution checks, and stressed
drawdown checks into one JSON report.
