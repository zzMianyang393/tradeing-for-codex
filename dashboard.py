from __future__ import annotations

import argparse
import html
import json
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
            },
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
      --primary: #5e6ad2;
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
      background:
        radial-gradient(800px circle at 20% -10%, rgba(94, 106, 210, 0.12), transparent 35%),
        var(--surface);
      box-shadow: 0 16px 50px rgba(0, 0, 0, 0.25);
    }}
    .card-inner {{ padding: 16px; }}
    .metric-label {{ color: var(--muted); font-size: 12px; }}
    .metric-value {{ margin-top: 8px; font-size: 26px; font-weight: 700; }}
    .metric-sub {{ margin-top: 4px; color: var(--muted); font-size: 12px; }}
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
      <div class="status">Health: {e(status)} · {e(health.get("issue_count", 0))} issues</div>
    </header>

    <section class="grid metrics">
      {metric_card("Equity", money(account.get("equity")), "Latest account snapshot")}
      {metric_card("Available", money(account.get("available_margin")), "Margin ready")}
      {metric_card("Used Margin", money(account.get("used_margin")), "Current exposure")}
      {metric_card("Open Positions", account.get("open_positions", 0), "Local account view")}
    </section>

    <section class="grid main">
      <div class="stack">
        {table_card("Open Positions", ["Symbol", "Side", "Notional", "Margin"], [_position_row(p) for p in positions])}
        {table_card("Recent Trades", ["Symbol", "Side", "PnL", "Exit"], [_trade_row(t) for t in trades])}
      </div>
      <div class="stack">
        {summary_card(trade_summary)}
        {table_card("Health Alerts", ["Severity", "Kind", "Message"], [_alert_row(a) for a in alerts])}
        {table_card("Risk Events", ["Type", "Detail"], [_risk_row(r) for r in risk_events])}
      </div>
    </section>
  </div>
</body>
</html>
"""


def write_dashboard(db_path: Path, out_path: Path) -> Path:
    payload = build_dashboard_payload(db_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_dashboard_html(payload), encoding="utf-8")
    return out_path


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
      <div class="metric-sub">Win rate {pct(summary.get("win_rate", 0.0))} · Total PnL {money(summary.get("total_pnl", 0.0))}</div>
    </div></article>"""


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
    args = parser.parse_args(argv)
    write_dashboard(args.db, args.out)
    print(f"Wrote dashboard to {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
