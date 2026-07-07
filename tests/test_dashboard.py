from __future__ import annotations

import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from dashboard import build_dashboard_payload, create_dashboard_server, render_dashboard_html, write_dashboard
from state_db import StateDB


class TestDashboard(unittest.TestCase):
    def test_build_dashboard_payload_summarizes_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.snapshot_account(equity=101.5, available_margin=90.0, used_margin=11.5, open_positions=1)
                db.snapshot_account(equity=103.0, available_margin=91.0, used_margin=12.0, open_positions=1)
                db.save_position("BTC-USDT-SWAP", "long", 50000.0, 0.001, 50.0, 5.0, 10.0)
                db.save_trade(
                    "BTC-USDT-SWAP",
                    "long",
                    50000.0,
                    50100.0,
                    "2026-07-06 10:00:00",
                    "2026-07-06 11:00:00",
                    0.1,
                    2.0,
                    signal_reason="range_revert_long",
                    exit_reason="take_profit",
                )
                report_id = db.save_health_report({"status": "critical", "issues": [{"kind": "api_failure"}]})
                db.save_health_alert(report_id, "critical", "api_failure", "Exchange unavailable", {})
            finally:
                db.close()

            payload = build_dashboard_payload(db_path)

        self.assertEqual(103.0, payload["account"]["equity"])
        self.assertEqual(1, payload["account"]["open_positions"])
        self.assertEqual(2, len(payload["equity_series"]))
        self.assertEqual(103.0, payload["equity_series"][-1]["equity"])
        self.assertEqual("critical", payload["health"]["status"])
        self.assertEqual(1, len(payload["positions"]))
        self.assertEqual(1, payload["trade_summary"]["total"])
        self.assertEqual("api_failure", payload["alerts"][0]["kind"])

    def test_render_dashboard_html_contains_operational_sections(self):
        payload = {
            "account": {"equity": 100.0, "available_margin": 80.0, "used_margin": 20.0, "open_positions": 1},
            "trade_summary": {"total": 2, "win_rate": 0.5, "total_pnl": 1.2},
            "positions": [{"symbol": "BTC-USDT-SWAP", "direction": "long", "notional": 50.0, "margin": 5.0}],
            "recent_trades": [{"symbol": "ETH-USDT-SWAP", "direction": "short", "pnl": 0.2, "exit_reason": "take_profit"}],
            "risk_events": [{"event_type": "reject", "detail": "{\"reason\":\"volatility\"}"}],
            "alerts": [{"severity": "critical", "kind": "api_failure", "message": "Exchange unavailable"}],
            "health": {"status": "critical", "issue_count": 1},
            "equity_series": [
                {"ts": "2026-07-06 10:00:00", "equity": 100.0},
                {"ts": "2026-07-06 11:00:00", "equity": 101.2},
            ],
        }

        html = render_dashboard_html(payload)

        self.assertIn("Trading Dashboard", html)
        self.assertIn("BTC-USDT-SWAP", html)
        self.assertIn("ETH-USDT-SWAP", html)
        self.assertIn("api_failure", html)
        self.assertIn("id=\"dashboard-data\"", html)
        self.assertIn("id=\"equity-chart\"", html)
        self.assertIn("id=\"table-search\"", html)
        self.assertIn("data-view-button=\"positions\"", html)
        self.assertIn("function setView", html)

    def test_render_dashboard_json_payload_escapes_script_closers(self):
        payload = {
            "account": {},
            "trade_summary": {},
            "positions": [],
            "recent_trades": [],
            "risk_events": [],
            "alerts": [{"severity": "critical", "kind": "xss", "message": "</script><script>alert(1)</script>"}],
            "health": {},
            "equity_series": [],
        }

        html = render_dashboard_html(payload)

        self.assertIn("id=\"dashboard-data\"", html)
        self.assertNotIn("</script><script>alert(1)</script>", html)

    def test_write_dashboard_creates_html_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            out_path = Path(tmp) / "dashboard.html"
            db = StateDB(db_path)
            try:
                db.snapshot_account(equity=10.0, available_margin=10.0, used_margin=0.0)
            finally:
                db.close()

            written = write_dashboard(db_path, out_path)

            self.assertEqual(out_path, written)
            self.assertTrue(out_path.exists())
            self.assertIn("Trading Dashboard", out_path.read_text(encoding="utf-8"))

    def test_dashboard_server_serves_html_and_json_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.snapshot_account(equity=12.5, available_margin=10.0, used_margin=2.5)
            finally:
                db.close()

            server = create_dashboard_server(db_path, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urllib.request.urlopen(f"http://{host}:{port}/api/dashboard", timeout=5) as response:
                    payload = response.read().decode("utf-8")
                    content_type = response.headers["Content-Type"]
                with urllib.request.urlopen(f"http://{host}:{port}/", timeout=5) as response:
                    html = response.read().decode("utf-8")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertIn("application/json", content_type)
        self.assertIn("\"equity\":12.5", payload)
        self.assertIn("Trading Dashboard", html)


if __name__ == "__main__":
    unittest.main()
