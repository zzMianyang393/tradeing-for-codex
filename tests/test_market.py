import csv
import tempfile
import unittest
from pathlib import Path

from market import load_market


class MarketLoaderTests(unittest.TestCase):
    def test_loads_quantify_15m_csv_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            path = data_dir / "BTC_15m.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for i in range(230):
                    ts = 1_704_067_200_000 + i * 15 * 60_000
                    price = 100 + i * 0.1
                    writer.writerow([ts, price, price + 1, price - 1, price + 0.2, 10])

            market = load_market(data_dir, 15)

            self.assertIn("BTC-USDT-SWAP", market)
            self.assertEqual(230, len(market["BTC-USDT-SWAP"]))
            self.assertGreater(market["BTC-USDT-SWAP"][0].volume_quote, 1000)

    def test_load_market_can_attach_funding_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            price_path = data_dir / "BTC_15m.csv"
            funding_path = data_dir / "BTC-USDT-SWAP_funding.csv"
            with price_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for i in range(4):
                    ts = 1_704_067_200_000 + i * 15 * 60_000
                    writer.writerow([ts, 100, 101, 99, 100, 10])
            with funding_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["symbol", "timestamp_ms", "timestamp_utc", "funding_rate", "realized_rate"])
                writer.writerow(["BTC-USDT-SWAP", 1_704_067_200_000, "2024-01-01 00:00:00", "0.0001", "0.00009"])
                writer.writerow(["BTC-USDT-SWAP", 1_704_067_200_000 + 30 * 60_000, "2024-01-01 00:30:00", "-0.0002", "-0.0002"])

            market = load_market(data_dir, 15, include_funding=True)

            bars = market["BTC-USDT-SWAP"]
            self.assertTrue(hasattr(bars[0], "funding_rate"))
            self.assertAlmostEqual(0.0001, bars[0].funding_rate)
            self.assertAlmostEqual(-0.0002, bars[-1].funding_rate)


if __name__ == "__main__":
    unittest.main()
