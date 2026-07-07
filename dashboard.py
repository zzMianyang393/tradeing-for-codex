from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from state_db import StateDB


def build_dashboard_payload(db_path: Path) -> dict[str, Any]:
    db = StateDB(db_path)
    try:
        history = db.get_account_history()
        latest = history[-1] if history else {}
        health_reports = db.get_recent_health_reports(1)
        latest_health = health_reports[0] if health_reports else {}
        return {
            "account": {
                "equity": latest.get("equity", 0.0),
                "available_margin": latest.get("available_margin", 0.0),
                "used_margin": latest.get("used_margin", 0.0),
                "open_positions": latest.get("open_positions", len(db.get_open_positions())),
                "daily_pnl": latest.get("daily_pnl"),
                "weekly_pnl": latest.get("weekly_pnl"),
                "risk_status": latest.get("risk_status"),
            },
            "equity_series": [
                {
                    "ts": row.get("ts", ""),
                    "equity": row.get("equity", 0.0),
                    "available_margin": row.get("available_margin", 0.0),
                    "used_margin": row.get("used_margin", 0.0),
                    "open_positions": row.get("open_positions", 0),
                }
                for row in history[-120:]
            ],
            "trade_summary": db.trade_summary(),
            "positions": db.get_open_positions(),
            "recent_trades": db.get_recent_trades(12),
            "risk_events": db.get_risk_events(10),
            "alerts": db.get_recent_health_alerts(10),
            "health": {
                "status": latest_health.get("status", "unknown"),
                "issue_count": latest_health.get("issue_count", 0),
            },
        }
    finally:
        db.close()


def render_dashboard_html(payload: dict[str, Any]) -> str:
    account = payload.get("account", {})
    trade_summary = payload.get("trade_summary", {})
    positions = payload.get("positions", [])
    trades = payload.get("recent_trades", [])
    risk_events = payload.get("risk_events", [])
    alerts = payload.get("alerts", [])
    health = payload.get("health", {})
    status = str(health.get("status", "unknown"))
    dashboard_json = safe_json(payload)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trading Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080808;
      --surface: #161618;
      --surface-2: #1d1d21;
      --border: #29292d;
      --text: #f4f4f5;
      --muted: #a1a1aa;
      --primary: #7c8cff;
      --success: #27b074;
      --warning: #f36d40;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    .shell {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 8px 0 20px;
      border-bottom: 1px solid var(--border);
    }}
    h1 {{ margin: 0; font-size: 24px; font-weight: 650; }}
    h2 {{ margin: 0 0 12px; font-size: 14px; font-weight: 600; color: #d9d9df; }}
    .status {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 32px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
      color: {status_color(status)};
      font-size: 13px;
      font-weight: 650;
      text-transform: uppercase;
    }}
    .grid {{ display: grid; gap: 16px; margin-top: 18px; }}
    .metrics {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .main {{ grid-template-columns: minmax(0, 1.35fr) minmax(360px, 0.65fr); }}
    .card {{
      position: relative;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: 0 16px 50px rgba(0, 0, 0, 0.25);
    }}
    .card-inner {{ padding: 16px; }}
    .section-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .metric-label {{ color: var(--muted); font-size: 12px; }}
    .metric-value {{ margin-top: 8px; font-size: 26px; font-weight: 700; }}
    .metric-sub {{ margin-top: 4px; color: var(--muted); font-size: 12px; }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: 18px;
      flex-wrap: wrap;
    }}
    .segmented {{
      display: inline-flex;
      min-height: 36px;
      padding: 3px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
    }}
    button {{
      min-height: 28px;
      padding: 0 10px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--muted);
      font: inherit;
      font-size: 13px;
      cursor: pointer;
    }}
    button.active {{ background: var(--surface-2); color: var(--text); }}
    input {{
      width: min(360px, 100%);
      min-height: 36px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
      color: var(--text);
      font: inherit;
      font-size: 13px;
    }}
    .chart-wrap {{ width: 100%; min-height: 260px; }}
    canvas {{ display: block; width: 100%; height: 240px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{
      padding: 11px 10px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      font-size: 13px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    tr:last-child td {{ border-bottom: 0; }}
    .stack {{ display: grid; gap: 16px; }}
    .pill {{
      display: inline-flex;
      max-width: 100%;
      align-items: center;
      min-height: 24px;
      padding: 0 8px;
      border-radius: 8px;
      background: var(--surface-2);
      border: 1px solid var(--border);
      color: #d9d9df;
      font-size: 12px;
    }}
    .empty {{ color: var(--muted); font-size: 13px; padding: 12px 0; }}
    .alert {{ color: var(--warning); }}
    .positive {{ color: var(--success); }}
    .negative {{ color: var(--warning); }}
    [data-view][hidden] {{ display: none; }}
    @media (max-width: 960px) {{
      .shell {{ padding: 16px; }}
      header {{ align-items: flex-start; flex-direction: column; }}
      .metrics, .main {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <div>
        <h1>Trading Dashboard</h1>
      </div>
      <div class="status">Health: {e(status)} &middot; {e(health.get("issue_count", 0))} issues</div>
    </header>

    <section class="grid metrics">
      {metric_card("Equity", money(account.get("equity")), "Latest account snapshot")}
      {metric_card("Available", money(account.get("available_margin")), "Margin ready")}
      {metric_card("Used Margin", money(account.get("used_margin")), "Current exposure")}
      {metric_card("Open Positions", account.get("open_positions", 0), "Local account view")}
    </section>

    {chart_card()}

    <section class="toolbar">
      <div class="segmented" role="tablist" aria-label="Dashboard views">
        <button type="button" class="active" data-view-button="positions">Positions</button>
        <button type="button" data-view-button="trades">Trades</button>
        <button type="button" data-view-button="alerts">Alerts</button>
      </div>
      <input id="table-search" type="search" placeholder="Filter visible rows" autocomplete="off">
    </section>

    <section class="grid main">
      <div class="stack" data-view="positions">
        {table_card("Open Positions", ["Symbol", "Side", "Notional", "Margin"], [_position_row(p) for p in positions])}
      </div>
      <div class="stack" data-view="trades" hidden>
        {table_card("Recent Trades", ["Symbol", "Side", "PnL", "Exit"], [_trade_row(t) for t in trades])}
      </div>
      <div class="stack" data-view="alerts" hidden>
        {summary_card(trade_summary)}
        {table_card("Health Alerts", ["Severity", "Kind", "Message"], [_alert_row(a) for a in alerts])}
        {table_card("Risk Events", ["Type", "Detail"], [_risk_row(r) for r in risk_events])}
      </div>
    </section>
  </div>
  <script id="dashboard-data" type="application/json">{dashboard_json}</script>
  <script>
    const dashboardData = JSON.parse(document.getElementById("dashboard-data").textContent);
    const search = document.getElementById("table-search");

    function setView(name) {{
      document.querySelectorAll("[data-view]").forEach((section) => {{
        section.hidden = section.dataset.view !== name;
      }});
      document.querySelectorAll("[data-view-button]").forEach((button) => {{
        button.classList.toggle("active", button.dataset.viewButton === name);
      }});
      filterVisibleRows();
    }}

    function filterVisibleRows() {{
      const query = (search.value || "").toLowerCase();
      document.querySelectorAll("[data-view]:not([hidden]) tbody tr").forEach((row) => {{
        row.hidden = query.length > 0 && !row.textContent.toLowerCase().includes(query);
      }});
    }}

    function drawEquityChart() {{
      const canvas = document.getElementById("equity-chart");
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * ratio));
      canvas.height = Math.max(1, Math.floor(rect.height * ratio));
      const ctx = canvas.getContext("2d");
      ctx.scale(ratio, ratio);
      ctx.clearRect(0, 0, rect.width, rect.height);
      const points = (dashboardData.equity_series || []).filter((point) => Number.isFinite(Number(point.equity)));
      if (points.length === 0) return;
      const values = points.map((point) => Number(point.equity));
      const min = Math.min(...values);
      const max = Math.max(...values);
      const span = Math.max(0.0001, max - min);
      const pad = 18;
      ctx.strokeStyle = "#29292d";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad, rect.height - pad);
      ctx.lineTo(rect.width - pad, rect.height - pad);
      ctx.stroke();
      ctx.strokeStyle = "#7c8cff";
      ctx.lineWidth = 2;
      ctx.beginPath();
      values.forEach((value, index) => {{
        const x = pad + (points.length === 1 ? 0 : index * (rect.width - pad * 2) / (points.length - 1));
        const y = rect.height - pad - ((value - min) / span) * (rect.height - pad * 2);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }});
      ctx.stroke();
    }}

    document.querySelectorAll("[data-view-button]").forEach((button) => {{
      button.addEventListener("click", () => setView(button.dataset.viewButton));
    }});
    search.addEventListener("input", filterVisibleRows);
    window.addEventListener("resize", drawEquityChart);
    drawEquityChart();
  </script>
</body>
</html>
"""


def write_dashboard(db_path: Path, out_path: Path) -> Path:
    payload = build_dashboard_payload(db_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_dashboard_html(payload), encoding="utf-8")
    return out_path


def create_dashboard_server(db_path: Path, host: str = "127.0.0.1", port: int = 8090) -> ThreadingHTTPServer:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self._send_html(render_dashboard_html(build_dashboard_payload(db_path)))
                return
            if self.path == "/api/dashboard":
                self._send_json(build_dashboard_payload(db_path))
                return
            self.send_error(404, "Not found")

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_html(self, body: str) -> None:
            self._send(200, "text/html; charset=utf-8", body.encode("utf-8"))

        def _send_json(self, payload: dict[str, Any]) -> None:
            self._send(200, "application/json; charset=utf-8", safe_json(payload).encode("utf-8"))

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), DashboardHandler)


def serve_dashboard(db_path: Path, host: str = "127.0.0.1", port: int = 8090) -> None:
    server = create_dashboard_server(db_path, host, port)
    actual_host, actual_port = server.server_address
    print(f"Serving dashboard at http://{actual_host}:{actual_port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def metric_card(label: str, value: Any, sub: str) -> str:
    return f"""<article class="card"><div class="card-inner">
      <div class="metric-label">{e(label)}</div>
      <div class="metric-value">{e(value)}</div>
      <div class="metric-sub">{e(sub)}</div>
    </div></article>"""


def summary_card(summary: dict[str, Any]) -> str:
    return f"""<article class="card"><div class="card-inner">
      <h2>Trade Summary</h2>
      <div class="metric-value">{e(summary.get("total", 0))} trades</div>
      <div class="metric-sub">Win rate {pct(summary.get("win_rate", 0.0))} &middot; Total PnL {money(summary.get("total_pnl", 0.0))}</div>
    </div></article>"""


def chart_card() -> str:
    return """<section class="grid">
      <article class="card"><div class="card-inner">
        <div class="section-head">
          <h2>Equity Curve</h2>
          <span class="pill">Local SQLite state</span>
        </div>
        <div class="chart-wrap"><canvas id="equity-chart" aria-label="Equity curve"></canvas></div>
      </div></article>
    </section>"""


def table_card(title: str, headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{e(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    if not rows:
        body = f"<tr><td colspan=\"{len(headers)}\"><div class=\"empty\">No records</div></td></tr>"
    return f"""<article class="card"><div class="card-inner">
      <h2>{e(title)}</h2>
      <table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
    </div></article>"""


def _position_row(position: dict[str, Any]) -> list[str]:
    return [
        e(position.get("symbol", "")),
        f"<span class=\"pill\">{e(position.get('direction', ''))}</span>",
        e(money(position.get("notional", 0.0))),
        e(money(position.get("margin", 0.0))),
    ]


def _trade_row(trade: dict[str, Any]) -> list[str]:
    pnl = float(trade.get("pnl") or 0.0)
    cls = "positive" if pnl >= 0 else "negative"
    return [
        e(trade.get("symbol", "")),
        e(trade.get("direction", "")),
        f"<span class=\"{cls}\">{e(money(pnl))}</span>",
        e(trade.get("exit_reason", "")),
    ]


def _alert_row(alert: dict[str, Any]) -> list[str]:
    return [
        f"<span class=\"alert\">{e(alert.get('severity', ''))}</span>",
        e(alert.get("kind", "")),
        e(alert.get("message", "")),
    ]


def _risk_row(event: dict[str, Any]) -> list[str]:
    return [e(event.get("event_type", "")), e(event.get("detail", ""))]


def e(value: Any) -> str:
    return html.escape(str(value))


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def money(value: Any) -> str:
    try:
        return f"{float(value):,.4f}"
    except (TypeError, ValueError):
        return "0.0000"


def pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def status_color(status: str) -> str:
    if status == "ok":
        return "var(--success)"
    if status in ("warning", "critical"):
        return "var(--warning)"
    return "var(--muted)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a local trading dashboard HTML file.")
    parser.add_argument("--db", type=Path, default=Path("reports") / "dry_run_state.db")
    parser.add_argument("--out", type=Path, default=Path("reports") / "dashboard.html")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args(argv)
    if args.serve:
        serve_dashboard(args.db, host=args.host, port=args.port)
        return 0
    write_dashboard(args.db, args.out)
    print(f"Wrote dashboard to {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
