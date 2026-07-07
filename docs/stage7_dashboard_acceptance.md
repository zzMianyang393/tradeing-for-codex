# Stage 7 Dashboard Acceptance

The first dashboard implementation is a dependency-free static HTML renderer
for local trading state.

## Implemented

- `dashboard.build_dashboard_payload` summarizes SQLite state into a dashboard
  payload.
- `dashboard.render_dashboard_html` renders a responsive dark operations
  dashboard.
- `dashboard.py --db reports\dry_run_state.db --out reports\dashboard.html`
  writes a browser-openable HTML file.
- `dashboard.py --serve --db reports\dry_run_state.db --host 127.0.0.1
  --port 8090` starts a dependency-free local HTTP dashboard.
- `GET /api/dashboard` returns the latest dashboard JSON payload with
  `Cache-Control: no-store`.
- The dashboard includes:
  - account equity and margin metrics
  - open positions
  - recent trades
  - trade summary
  - health alerts
  - risk events

## Current Limits

- It reads local SQLite only and does not query live exchange state directly.
- The local server intentionally uses Python standard library HTTP only; there
  is no Flask/FastAPI dependency.
- The page can be refreshed against the local server, but it does not yet patch
  table/chart content in place from the JSON endpoint.

## Next Step

- Add strategy and symbol performance breakdown panels.
- Add in-place browser polling from `/api/dashboard` for table/chart updates.
