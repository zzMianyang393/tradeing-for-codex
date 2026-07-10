from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from binance_cm_klines import download_klines, month_url


class BinanceCoinKlinesTests(unittest.TestCase):
    def test_month_url_uses_monthly_layout(self):
        self.assertIn("BTCUSD_PERP-1d-2024-07.zip", month_url("BTCUSD_PERP", 2024, 7))

    def test_download_klines_writes_sorted_selected_days(self):
        rows = [
            ["1720656000000", "1", "1", "1", "1", "1", "0", "0", "0", "0", "0", "0"],
            ["1720569600000", "1", "1", "1", "1", "1", "0", "0", "0", "0", "0", "0"],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with patch("binance_cm_klines._read_zip", return_value=rows):
                metadata = download_klines("BTCUSD_PERP", date(2024, 7, 10), date(2024, 7, 11), Path(tmp))
            with (Path(tmp) / "BTCUSD_PERP_binance_cm_1d.csv").open(encoding="utf-8") as handle:
                output = list(csv.DictReader(handle))
        self.assertEqual(2, metadata["rows"])
        self.assertEqual(["1720569600000", "1720656000000"], [row["open_time"] for row in output])


if __name__ == "__main__":
    unittest.main()
