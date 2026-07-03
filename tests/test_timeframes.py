import csv
import tempfile
import unittest
from pathlib import Path

from market import load_market


class TimeframeLoaderTests(unittest.TestCase):
    def test_loads_quantify_1h_csv_when_timeframe_is_60(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            path = data_dir / "ETH_1h.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for i in range(230):
                    ts = 1_704_067_200_000 + i * 60 * 60_000
                    price = 2000 + i
                    writer.writerow([ts, price, price + 3, price - 3, price + 1, 4])

            market = load_market(data_dir, 60)

            self.assertIn("ETH-USDT-SWAP", market)
            self.assertEqual(230, len(market["ETH-USDT-SWAP"]))

    def test_normalizes_short_quantify_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            path = data_dir / "ETH_1h.csv"
            with path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for i in range(230):
                    ts = 1_704_067 + i * 36
                    writer.writerow([ts, 2000, 2003, 1997, 2001, 4])

            market = load_market(data_dir, 60)

            self.assertEqual(1_704_067_000_000, market["ETH-USDT-SWAP"][0].ts)


if __name__ == "__main__":
    unittest.main()
