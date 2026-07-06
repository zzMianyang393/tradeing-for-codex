# Stage 4 Health Report Acceptance

Stage 4 starts the monitoring layer for OKX simulated trading. The current
implementation is a local, machine-readable health report that can run without
submitting orders.

## Implemented

- `health_report.build_health_report` converts runtime state into a stable
  status payload.
- `runner.py --okx-health-report --db reports\dry_run_state.db` prints JSON for
  OKX simulated trading health.
- Status levels are `ok`, `warning`, and `critical`.
- Critical issues:
  - OKX API failure while reading positions.
  - Local SQLite open positions drifting from OKX simulated positions.
- Warning issues:
  - Active exchange orders older than the configured stale-order threshold.
  - Risk manager pause status passed into the report builder.

## Current Limits

- The report is local JSON only; it does not send notifications.
- Risk pause detection is implemented in the pure report builder but is not yet
  wired to a persisted runtime risk-state source.
- Stale-order threshold uses the default 30 minutes and is not yet exposed as a
  CLI flag.

## Next Step

Add alert delivery and persistence:

- Save health report snapshots into SQLite.
- Add configurable stale-order and drift thresholds.
- Emit alert events for repeated `warning` or any `critical` status.
- Add a dry-run notification adapter before wiring external channels.
