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


if __name__ == "__main__":
    unittest.main()
