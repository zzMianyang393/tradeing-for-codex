# Stage 3 Simulated Execution Acceptance

This document records the current acceptance state for Stage 3: simulated
execution. The scope is OKX simulated trading plus the local dry-run execution
path. It is not a live-trading approval.

## Completed Capabilities

- Local dry-run runner:
  - `python runner.py --once --db reports\dry_run_state.db --equity 25`
  - `python runner.py --loop --iterations 3 --interval 0 --db reports\dry_run_state.db --equity 25`
  - `python runner.py --status --db reports\dry_run_state.db`
  - `python runner.py --reconcile --db reports\dry_run_state.db`
- OKX simulated connectivity:
  - `python runner.py --okx-check --okx-symbol BTC-USDT-SWAP`
  - `python runner.py --reconcile --exchange okx --db reports\dry_run_state.db`
- OKX simulated order smoke test:
  - `python runner.py --okx-smoke-order --confirm-okx-smoke-order --okx-symbol BTC-USDT-SWAP --okx-smoke-direction long --okx-smoke-qty 0.001 --okx-smoke-price 1 --okx-smoke-notional 1 --okx-smoke-margin 1`
- Protected manual signal submission:
  - `python runner.py --okx-submit-signal --confirm-okx-submit-signal --db reports\dry_run_state.db --okx-symbol BTC-USDT-SWAP --okx-signal-direction long --okx-signal-price 50000 --okx-signal-notional 10 --okx-signal-margin 1 --okx-signal-leverage 10`
- Order state synchronization:
  - `python runner.py --okx-sync-orders --db reports\dry_run_state.db`
  - Filled open orders create local open positions.
  - Filled close orders close local positions and create trade records.
- Protected position close submission:
  - `python runner.py --okx-close-position --confirm-okx-close-position --db reports\dry_run_state.db --position-id <local_position_id> --okx-close-price 50100`
- Runtime snapshot and finite monitor loop:
  - `python runner.py --okx-snapshot --db reports\dry_run_state.db`
  - `python runner.py --okx-monitor-loop --iterations 3 --interval 5 --db reports\dry_run_state.db`

## Safety Gates

- OKX commands use simulated trading credentials and the OKX simulated trading
  header.
- Order-submitting commands require explicit confirmation flags.
- Signal submission reconciles local positions against OKX simulated positions
  before placing an order.
- Signal submission uses `RiskManager.check_order` before order placement.
- Close submission reconciles local positions against OKX simulated positions
  before placing the close order.
- Missing OKX credentials return structured JSON errors instead of tracebacks.
- OKX API errors return structured JSON errors for runner commands.

## Persistence Guarantees

- `StateDB` stores orders, exchange order ids, positions, account snapshots,
  trades, and risk events.
- Live/pending exchange orders can be queried with
  `StateDB.get_active_exchange_orders()`.
- OKX order synchronization updates local order status, fill price, fill size,
  and fee.
- Filled open orders are persisted as local positions.
- Filled close orders close local positions and persist trade rows.
- Runtime snapshots write OKX account state and local monitoring metrics into
  `account_snapshots`.

## Verification Commands

Run these before treating Stage 3 changes as ready:

```bash
python -m unittest discover -s tests
python -m py_compile runner.py exchange.py executor.py backtester.py risk_manager.py state_db.py config.py
git diff --check
```

Expected state as of this document:

- Unit test suite passes.
- Python compile check passes.
- Diff whitespace check passes.
- Worktree may contain a local untracked `reports\dry_run_state.db` smoke-test
  database; it must not be committed.

## Known Limits

- The OKX path is still simulated trading only.
- Automatic strategy signal generation is not yet wired into the OKX runner.
- There is no long-running daemon or alerting service yet.
- There is no production secret management; credentials are read from local
  environment variables.
- Order/position reconciliation compares symbol and direction, not full quantity
  and margin parity.
- Real exchange behavior must be validated with tiny simulated orders before
  increasing notional.

## Stage 4 Entry Criteria

Stage 4 can start once Stage 3 verification commands pass. The next stage should
focus on:

- Monitoring and alerting for account, order, position, and risk state.
- Structured health reports for scheduled runs.
- Alert thresholds for stale orders, reconciliation drift, drawdown, and API
  failures.
- Safer configuration and secret handling for unattended operation.
- Dashboard or report files that summarize the current runtime state.
