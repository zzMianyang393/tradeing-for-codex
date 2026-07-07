from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import report_cli
from state_db import StateDB


class TestReportCliSummaries(unittest.TestCase):
    def test_daily_filters_trades_by_exit_date_for_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.save_trade("BTC-USDT-SWAP", "long", 100.0, 102.0, "2026-07-07 09:00:00", "2026-07-07 10:00:00", 2.0, 2.0)
                db.save_trade("ETH-USDT-SWAP", "long", 100.0, 99.0, "2026-07-06 09:00:00", "2026-07-06 10:00:00", -1.0, -1.0)
            finally:
                db.close()
            output = io.StringIO()
            args = Namespace(db_path=str(db_path), date="2026-07-07", json=True)

            with contextlib.redirect_stdout(output):
                report_cli.cmd_daily(args)

            payload = json.loads(output.getvalue())
            self.assertEqual(1, payload["total_trades"])
            self.assertEqual(2.0, payload["total_pnl"])
            self.assertEqual({"BTC-USDT-SWAP": {"count": 1, "pnl": 2.0, "wins": 1}}, payload["by_symbol"])

    def test_weekly_filters_to_week_containing_requested_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"
            db = StateDB(db_path)
            try:
                db.save_trade("BTC-USDT-SWAP", "long", 100.0, 102.0, "2026-07-07 09:00:00", "2026-07-07 10:00:00", 2.0, 2.0, signal_reason="range")
                db.save_trade("ETH-USDT-SWAP", "short", 100.0, 98.0, "2026-07-06 09:00:00", "2026-07-06 10:00:00", 1.0, 1.0, signal_reason="range")
                db.save_trade("SOL-USDT-SWAP", "long", 100.0, 99.0, "2026-07-05 09:00:00", "2026-07-05 10:00:00", -1.0, -1.0, signal_reason="old")
            finally:
                db.close()
            output = io.StringIO()
            args = Namespace(db_path=str(db_path), date="2026-07-07", json=True)

            with contextlib.redirect_stdout(output):
                report_cli.cmd_weekly(args)

            payload = json.loads(output.getvalue())
            self.assertEqual(2, payload["total_trades"])
            self.assertEqual(3.0, payload["total_pnl"])
            self.assertEqual({"range": {"count": 2, "pnl": 3.0, "wins": 2}}, payload["by_reason"])

    def test_audit_runs_rolling_audit_and_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "audit.json"
            args = Namespace(
                db_path="unused.db",
                data=Path("data"),
                out=out_path,
                stride_days=7,
                max_windows=2,
                warmup_days=30,
                json=True,
                module="default",
            )
            fake_report = {"windows": {}, "ok": True}
            output = io.StringIO()

            with patch("report_cli.run_rolling_audit", return_value=fake_report) as audit:
                with contextlib.redirect_stdout(output):
                    report_cli.cmd_audit(args)

            audit.assert_called_once()
            self.assertEqual(fake_report, json.loads(out_path.read_text(encoding="utf-8")))
            self.assertEqual(fake_report, json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
