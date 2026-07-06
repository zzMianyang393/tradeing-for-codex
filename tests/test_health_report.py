from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from health_report import build_health_report
from state_db import ReconcileResult


@dataclass(frozen=True)
class _RiskStatus:
    is_paused: bool = False
    pause_reason: str = ""


class TestHealthReport(unittest.TestCase):
    def test_ok_when_no_health_issues_are_present(self):
        report = build_health_report(
            active_orders=[],
            reconciliation=ReconcileResult(matches=[], local_only=[], exchange_only=[], consistent=True),
            risk_status=_RiskStatus(),
            now=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual("ok", report.status)
        self.assertEqual([], report.issues)

    def test_stale_active_order_generates_warning(self):
        report = build_health_report(
            active_orders=[
                {
                    "id": "order-1",
                    "symbol": "BTC-USDT-SWAP",
                    "status": "live",
                    "created_at": "2026-07-06 10:59:00",
                    "exchange_order_id": "okx-1",
                }
            ],
            now=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
            stale_order_minutes=30,
        )

        self.assertEqual("warning", report.status)
        self.assertEqual("stale_order", report.issues[0].kind)
        self.assertEqual("warning", report.issues[0].severity)
        self.assertEqual("order-1", report.issues[0].context["order_id"])

    def test_reconciliation_drift_is_critical(self):
        report = build_health_report(
            active_orders=[],
            reconciliation=ReconcileResult(
                matches=[],
                local_only=[{"symbol": "ETH-USDT-SWAP", "direction": "long"}],
                exchange_only=[],
                consistent=False,
            ),
            now=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual("critical", report.status)
        self.assertEqual("reconciliation_drift", report.issues[0].kind)
        self.assertEqual("critical", report.issues[0].severity)

    def test_api_failure_is_critical(self):
        report = build_health_report(
            active_orders=[],
            api_error="OKX error 500: unavailable",
            now=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual("critical", report.status)
        self.assertEqual("api_failure", report.issues[0].kind)
        self.assertIn("unavailable", report.issues[0].message)

    def test_risk_pause_generates_warning(self):
        report = build_health_report(
            active_orders=[],
            risk_status=_RiskStatus(is_paused=True, pause_reason="daily loss limit"),
            now=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual("warning", report.status)
        self.assertEqual("risk_paused", report.issues[0].kind)
        self.assertEqual("daily loss limit", report.issues[0].context["reason"])


if __name__ == "__main__":
    unittest.main()
