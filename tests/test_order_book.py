from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market import FeatureBar
from order_book import (
    OrderBookSnapshot,
    add_order_book_features,
    append_order_book_snapshot,
    load_order_book_snapshots,
    main,
    parse_order_book_snapshot,
    save_order_book_snapshots,
)


class TestOrderBook(unittest.TestCase):
    def test_parse_okx_order_book_snapshot(self):
        snapshot = parse_order_book_snapshot(
            "BTC-USDT-SWAP",
            {
                "ts": "1700000000000",
                "bids": [["99.5", "2"], ["99.0", "1"]],
                "asks": [["100.5", "3"], ["101.0", "1"]],
            },
        )

        self.assertEqual("BTC-USDT-SWAP", snapshot.symbol)
        self.assertEqual(1_700_000_000_000, snapshot.ts)
        self.assertAlmostEqual(99.5, snapshot.best_bid)
        self.assertAlmostEqual(100.5, snapshot.best_ask)
        self.assertAlmostEqual(1.0 / 100.0, snapshot.spread_pct)
        self.assertAlmostEqual(298.0, snapshot.bid_depth_quote)
        self.assertAlmostEqual(402.5, snapshot.ask_depth_quote)

    def test_save_and_load_order_book_snapshots(self):
        snapshots = [
            OrderBookSnapshot(
                symbol="BTC-USDT-SWAP",
                ts=1_700_000_000_000,
                time="2023-11-14 22:13:20",
                best_bid=99.5,
                best_ask=100.5,
                spread_pct=0.01,
                bid_depth_quote=298.0,
                ask_depth_quote=402.5,
                depth_imbalance=-0.1492,
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTC-USDT-SWAP_order_book.csv"
            save_order_book_snapshots(path, snapshots)
            loaded = load_order_book_snapshots(path)

        self.assertEqual(snapshots, loaded)

    def test_add_order_book_features_uses_latest_snapshot(self):
        bars = [
            FeatureBar(ts=1000, time="t1", open=1, high=1, low=1, close=1, volume_quote=1),
            FeatureBar(ts=2000, time="t2", open=1, high=1, low=1, close=1, volume_quote=1),
            FeatureBar(ts=3000, time="t3", open=1, high=1, low=1, close=1, volume_quote=1),
        ]
        snapshots = [
            OrderBookSnapshot("BTC-USDT-SWAP", 1500, "s1", 99, 101, 0.02, 100, 200, -1.0 / 3.0),
            OrderBookSnapshot("BTC-USDT-SWAP", 2500, "s2", 98, 102, 0.04, 300, 100, 0.5),
        ]

        enriched = add_order_book_features(bars, snapshots)

        self.assertEqual(0.0, enriched[0].order_book_spread_pct)
        self.assertEqual(0.02, enriched[1].order_book_spread_pct)
        self.assertEqual(0.04, enriched[2].order_book_spread_pct)
        self.assertEqual(300.0, enriched[2].bid_depth_quote)
        self.assertEqual(0.5, enriched[2].depth_imbalance)

    def test_append_order_book_snapshot_merges_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            page = {
                "ts": "1700000000000",
                "bids": [["99.5", "2"]],
                "asks": [["100.5", "3"]],
            }

            with patch("order_book.fetch_order_book_snapshot", return_value=page) as fetch:
                count = append_order_book_snapshot("BTC-USDT-SWAP", out_dir=out_dir)
                count_again = append_order_book_snapshot("BTC-USDT-SWAP", out_dir=out_dir)

            self.assertEqual(1, count)
            self.assertEqual(1, count_again)
            self.assertEqual(2, fetch.call_count)
            loaded = load_order_book_snapshots(out_dir / "BTC-USDT-SWAP_order_book.csv")
            self.assertEqual(1, len(loaded))

    def test_main_downloads_requested_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            page = {
                "ts": "1700000000000",
                "bids": [["99.5", "2"]],
                "asks": [["100.5", "3"]],
            }

            with patch("order_book.fetch_order_book_snapshot", return_value=page):
                code = main([
                    "--symbols",
                    "BTC-USDT-SWAP",
                    "--out",
                    str(out_dir),
                ])

            self.assertEqual(0, code)
            self.assertEqual(1, len(load_order_book_snapshots(out_dir / "BTC-USDT-SWAP_order_book.csv")))


if __name__ == "__main__":
    unittest.main()
