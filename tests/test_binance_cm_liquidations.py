from __future__ import annotations

import csv
import io
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from binance_cm_liquidations import archive_url, download_liquidations, fetch_day


def _archive_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("sample.csv", "time,side,order_type,time_in_force,original_quantity,price,average_price,order_status,last_fill_quantity,accumulated_fill_quantity\n1,BUY,LIMIT,IOC,2,1,1,FILLED,2,2\n2,SELL,LIMIT,IOC,3,1,1,FILLED,3,3\n")
    return output.getvalue()


class _Response:
    def __init__(self, payload: bytes): self.payload = payload
    def read(self) -> bytes: return self.payload
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class BinanceCoinLiquidationTests(unittest.TestCase):
    def test_archive_url_uses_daily_snapshot_layout(self):
        self.assertIn("BTCUSD_PERP-liquidationSnapshot-2024-07-10.zip", archive_url("BTCUSD_PERP", date(2024, 7, 10)))

    def test_fetch_day_aggregates_directional_counts(self):
        with patch("binance_cm_liquidations.urllib.request.urlopen", return_value=_Response(_archive_bytes())):
            result = fetch_day("BTCUSD_PERP", date(2024, 7, 10))
        self.assertEqual(2, result["total_count"] if result else None)
        self.assertEqual(3.0, result["sell_contracts"] if result else None)

    def test_download_writes_daily_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("binance_cm_liquidations.fetch_day", return_value={"buy_count": 1, "sell_count": 2, "buy_contracts": 1.0, "sell_contracts": 2.0, "total_count": 3, "total_contracts": 3.0}):
                metadata = download_liquidations("BTCUSD_PERP", date(2024, 7, 10), date(2024, 7, 10), Path(tmp))
            self.assertEqual(1, metadata["rows"])
            self.assertEqual(1.0, metadata["coverage_ratio"])


if __name__ == "__main__":
    unittest.main()
