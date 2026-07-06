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
- The dashboard includes:
  - account equity and margin metrics
  - open positions
  - recent trades
  - trade summary
  - health alerts
  - risk events

## Current Limits

- The dashboard is static HTML; it does not auto-refresh.
- There is no Flask/FastAPI server yet.
- It reads local SQLite only and does not query live exchange state directly.

## Next Step

- Add a tiny local web server with refreshable JSON endpoints.
- Add equity curve visualization from account snapshots.
- Add strategy and symbol performance breakdown panels.
