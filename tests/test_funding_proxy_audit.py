from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from funding_proxy_audit import audit_proxy, pearson
from funding_rate import FundingRate, save_funding_rates


class FundingProxyAuditTests(unittest.TestCase):
    def test_pearson_handles_perfect_alignment(self):
        self.assertEqual(1.0, pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]))

    def test_audit_requires_overlap_and_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            okx_path = root / "okx.csv"
            binance_path = root / "binance.csv"
            rates = [
                FundingRate("BTC-USDT-SWAP", index * 8 * 60 * 60 * 1000, "t", 0.001 * index, 0.0)
                for index in range(1, 91)
            ]
            save_funding_rates(okx_path, rates)
            with binance_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["source", "symbol", "timestamp_ms", "timestamp_utc", "funding_rate", "mark_price"])
                for index in range(1, 91):
                    writer.writerow(["binance", "BTCUSDT", index * 8 * 60 * 60 * 1000, "t", 0.001 * index, 0])
            result = audit_proxy(okx_path, binance_path)
        self.assertTrue(result["proxy_alignment_passed"])
        self.assertEqual(90, result["overlap_rows"])


if __name__ == "__main__":
    unittest.main()
