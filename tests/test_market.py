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

    def test_load_market_can_attach_open_interest_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            price_path = data_dir / "BTC_15m.csv"
            oi_path = data_dir / "BTC-USDT-SWAP_open_interest.csv"
            with price_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for i in range(4):
                    ts = 1_704_067_200_000 + i * 15 * 60_000
                    writer.writerow([ts, 100, 101, 99, 100, 10])
            with oi_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["symbol", "timestamp_ms", "timestamp_utc", "open_interest", "open_interest_currency"])
                writer.writerow(["BTC-USDT-SWAP", 1_704_067_200_000, "2024-01-01 00:00:00", "100", "10"])
                writer.writerow(["BTC-USDT-SWAP", 1_704_067_200_000 + 30 * 60_000, "2024-01-01 00:30:00", "120", "12"])

            market = load_market(data_dir, 15, include_open_interest=True)

            bars = market["BTC-USDT-SWAP"]
            self.assertTrue(hasattr(bars[0], "open_interest"))
            self.assertAlmostEqual(100.0, bars[0].open_interest)
            self.assertAlmostEqual(120.0, bars[-1].open_interest)
            self.assertAlmostEqual(0.2, bars[-1].open_interest_change_pct)

    def test_load_market_can_attach_trade_flow_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            price_path = data_dir / "BTC_15m.csv"
            trades_path = data_dir / "BTC-USDT-SWAP_trades.csv"
            with price_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for i in range(4):
                    ts = 1_704_067_200_000 + i * 15 * 60_000
                    writer.writerow([ts, 100, 101, 99, 100, 10])
            with trades_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["symbol", "trade_id", "timestamp_ms", "timestamp_utc", "side", "price", "size", "quote_volume"])
                writer.writerow(["BTC-USDT-SWAP", "1", 1_704_067_200_000, "2024-01-01 00:00:00", "buy", "100", "2", "200"])
                writer.writerow(["BTC-USDT-SWAP", "2", 1_704_067_200_000 + 10 * 60_000, "2024-01-01 00:10:00", "sell", "100", "1", "100"])

            market = load_market(data_dir, 15, include_trade_flow=True)

            bars = market["BTC-USDT-SWAP"]
            self.assertTrue(hasattr(bars[0], "active_buy_quote"))
            self.assertAlmostEqual(200.0, bars[0].active_buy_quote)
            self.assertAlmostEqual(100.0, bars[0].active_sell_quote)
            self.assertAlmostEqual(2.0 / 3.0, bars[0].active_buy_ratio)
            self.assertAlmostEqual(1.0 / 3.0, bars[0].trade_flow_imbalance)

    def test_load_market_can_attach_order_book_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            price_path = data_dir / "BTC_15m.csv"
            order_book_path = data_dir / "BTC-USDT-SWAP_order_book.csv"
            with price_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for i in range(4):
                    ts = 1_704_067_200_000 + i * 15 * 60_000
                    writer.writerow([ts, 100, 101, 99, 100, 10])
            with order_book_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["symbol", "timestamp_ms", "timestamp_utc", "best_bid", "best_ask", "spread_pct", "bid_depth_quote", "ask_depth_quote", "depth_imbalance"])
                writer.writerow(["BTC-USDT-SWAP", 1_704_067_200_000, "2024-01-01 00:00:00", "99", "101", "0.02", "100", "200", "-0.333333"])

            market = load_market(data_dir, 15, include_order_book=True)

            bars = market["BTC-USDT-SWAP"]
            self.assertTrue(hasattr(bars[0], "order_book_spread_pct"))
            self.assertAlmostEqual(0.02, bars[0].order_book_spread_pct)
            self.assertAlmostEqual(100.0, bars[0].bid_depth_quote)
            self.assertAlmostEqual(-0.333333, bars[0].depth_imbalance)


if __name__ == "__main__":
    unittest.main()
