from __future__ import annotations

import csv
import io
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from binance_cm_metrics import archive_url, download_metrics, fetch_day, field_coverage


def _archive_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("BTCUSD_PERP-metrics-2024-07-10.csv", "create_time,symbol,sum_open_interest\n2024-07-10,BTCUSD_PERP,12\n")
    return output.getvalue()


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class BinanceCoinMetricsTests(unittest.TestCase):
    def test_archive_url_has_expected_daily_layout(self):
        self.assertIn("BTCUSD_PERP-metrics-2024-07-10.zip", archive_url("BTCUSD_PERP", date(2024, 7, 10)))

    def test_fetch_day_reads_raw_metrics_schema(self):
        with patch("binance_cm_metrics.urllib.request.urlopen", return_value=_Response(_archive_bytes())):
            row = fetch_day("BTCUSD_PERP", date(2024, 7, 10))
        self.assertEqual("12", row["sum_open_interest"] if row else None)

    def test_download_metrics_preserves_source_and_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("binance_cm_metrics.fetch_day", return_value={"symbol": "BTCUSD_PERP", "sum_open_interest": "12"}):
                metadata = download_metrics("BTCUSD_PERP", date(2024, 7, 10), date(2024, 7, 10), Path(tmp), 0)
            self.assertEqual(1, metadata["rows"])
            self.assertIn("sum_open_interest", metadata["fieldnames"])

    def test_download_metrics_supports_resumable_parallel_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("binance_cm_metrics.fetch_day", return_value={"symbol": "BTCUSD_PERP"}):
                metadata = download_metrics("BTCUSD_PERP", date(2024, 7, 10), date(2024, 7, 11), Path(tmp), 0, workers=2)
            self.assertEqual(2, metadata["downloaded_this_run"])

    def test_field_coverage_reveals_late_arriving_columns(self):
        coverage = field_coverage(
            [{"oi": "1", "late": ""}, {"oi": "2", "late": "3"}],
            ["oi", "late"],
        )
        self.assertEqual(1.0, coverage["oi"]["coverage_ratio"])
        self.assertEqual(0.5, coverage["late"]["coverage_ratio"])


if __name__ == "__main__":
    unittest.main()
