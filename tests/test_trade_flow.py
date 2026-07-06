from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from market import FeatureBar
from trade_flow import (
    TradeTick,
    add_trade_flow_features,
    download_trade_ticks,
    load_trade_ticks,
    main,
    parse_trade_rows,
    save_trade_ticks,
)


class TestTradeFlow(unittest.TestCase):
    def test_parse_okx_trade_rows(self):
        ticks = parse_trade_rows(
            "BTC-USDT-SWAP",
            [
                {
                    "tradeId": "123",
                    "side": "buy",
                    "px": "50000.5",
                    "sz": "0.01",
                    "ts": "1700000000000",
                }
            ],
        )

        self.assertEqual(1, len(ticks))
        self.assertEqual("BTC-USDT-SWAP", ticks[0].symbol)
        self.assertEqual("123", ticks[0].trade_id)
        self.assertEqual("buy", ticks[0].side)
        self.assertAlmostEqual(500.005, ticks[0].quote_volume)

    def test_save_and_load_trade_ticks(self):
        ticks = [
            TradeTick(
                symbol="BTC-USDT-SWAP",
                trade_id="123",
                ts=1_700_000_000_000,
                time="2023-11-14 22:13:20",
                side="buy",
                price=50000.0,
                size=0.01,
                quote_volume=500.0,
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTC-USDT-SWAP_trades.csv"
            save_trade_ticks(path, ticks)
            loaded = load_trade_ticks(path)

        self.assertEqual(ticks, loaded)

    def test_add_trade_flow_features_aggregates_by_bar_window(self):
        bars = [
            FeatureBar(ts=1000, time="t1", open=1, high=1, low=1, close=1, volume_quote=100),
            FeatureBar(ts=2000, time="t2", open=1, high=1, low=1, close=1, volume_quote=200),
            FeatureBar(ts=3000, time="t3", open=1, high=1, low=1, close=1, volume_quote=300),
        ]
        ticks = [
            TradeTick("BTC-USDT-SWAP", "1", 1100, "x", "buy", 10.0, 2.0, 20.0),
            TradeTick("BTC-USDT-SWAP", "2", 1900, "x", "sell", 10.0, 1.0, 10.0),
            TradeTick("BTC-USDT-SWAP", "3", 2600, "x", "buy", 10.0, 3.0, 30.0),
        ]

        enriched = add_trade_flow_features(bars, ticks)

        self.assertEqual(20.0, enriched[0].active_buy_quote)
        self.assertEqual(10.0, enriched[0].active_sell_quote)
        self.assertAlmostEqual(2.0 / 3.0, enriched[0].active_buy_ratio)
        self.assertAlmostEqual(1.0 / 3.0, enriched[0].trade_flow_imbalance)
        self.assertEqual(30.0, enriched[1].active_buy_quote)
        self.assertEqual(0.0, enriched[1].active_sell_quote)

    def test_download_trade_ticks_merges_existing_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            existing = [
                TradeTick("BTC-USDT-SWAP", "1", 1_700_000_000_000, "old", "buy", 10.0, 1.0, 10.0),
            ]
            save_trade_ticks(out_dir / "BTC-USDT-SWAP_trades.csv", existing)
            page = [
                {"tradeId": "2", "side": "sell", "px": "10", "sz": "2", "ts": "1700000001000"},
                {"tradeId": "3", "side": "buy", "px": "20", "sz": "1", "ts": "1700000002000"},
            ]

            with patch("trade_flow.fetch_trade_page", return_value=page) as fetch:
                count = download_trade_ticks(
                    "BTC-USDT-SWAP",
                    out_dir=out_dir,
                    limit=100,
                )

            self.assertEqual(3, count)
            fetch.assert_called_once_with("BTC-USDT-SWAP", before=None, limit=100)
            loaded = load_trade_ticks(out_dir / "BTC-USDT-SWAP_trades.csv")
            self.assertEqual(["1", "2", "3"], [tick.trade_id for tick in loaded])

    def test_main_downloads_requested_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            page = [{"tradeId": "1", "side": "buy", "px": "10", "sz": "2", "ts": "1700000000000"}]

            with patch("trade_flow.fetch_trade_page", return_value=page):
                code = main([
                    "--symbols",
                    "BTC-USDT-SWAP",
                    "--out",
                    str(out_dir),
                ])

            self.assertEqual(0, code)
            self.assertEqual(1, len(load_trade_ticks(out_dir / "BTC-USDT-SWAP_trades.csv")))


if __name__ == "__main__":
    unittest.main()
