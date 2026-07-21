from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from okx_futures_calendar_spread_descriptive_audit import descriptive_audit


class OkxFuturesCalendarSpreadDescriptiveAuditTests(unittest.TestCase):
    def test_describes_spread_amplitude_against_cost_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spread.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["timestamp_ms", "future_inst_id", "spread_pct"])
                writer.writeheader()
                writer.writerow({"timestamp_ms": 1720656000000, "future_inst_id": "BTC-USDT-240927", "spread_pct": "0.001"})
                writer.writerow({"timestamp_ms": 1720742400000, "future_inst_id": "BTC-USDT-240927", "spread_pct": "-0.004"})
            report = descriptive_audit(path, cost_floor=0.0032)
        self.assertEqual(2, report["rows"])
        self.assertEqual(2, report["active_days"])
        self.assertEqual(1, report["abs_spread_ge_cost_rows"])
        self.assertEqual(0.5, report["abs_spread_ge_cost_ratio"])
        self.assertEqual("descriptive_only_not_strategy", report["decision"])


if __name__ == "__main__":
    unittest.main()
