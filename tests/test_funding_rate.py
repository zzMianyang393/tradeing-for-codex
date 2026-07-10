from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from funding_rate import (
    FundingRate,
    add_funding_features,
    download_funding_rates,
    main,
    load_funding_rates,
    parse_funding_rows,
    save_funding_rates,
)
from market import FeatureBar


class TestFundingRate(unittest.TestCase):
    def test_parse_okx_funding_rows(self):
        rows = parse_funding_rows(
            [
                {
                    "instId": "BTC-USDT-SWAP",
                    "fundingRate": "0.0001",
                    "realizedRate": "0.00009",
                    "fundingTime": "1700000000000",
                }
            ]
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("BTC-USDT-SWAP", rows[0].symbol)
        self.assertEqual(1_700_000_000_000, rows[0].ts)
        self.assertAlmostEqual(0.0001, rows[0].funding_rate)
        self.assertAlmostEqual(0.00009, rows[0].realized_rate)

    def test_save_and_load_funding_rates(self):
        rates = [
            FundingRate(
                symbol="BTC-USDT-SWAP",
                ts=1_700_000_000_000,
                time="2023-11-14 22:13:20",
                funding_rate=0.0001,
                realized_rate=0.00009,
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTC-USDT-SWAP_funding.csv"
            save_funding_rates(path, rates)
            loaded = load_funding_rates(path)

        self.assertEqual(rates, loaded)

    def test_add_funding_features_uses_latest_known_rate(self):
        bars = [
            FeatureBar(ts=1000, time="t1", open=1, high=1, low=1, close=1, volume_quote=1),
            FeatureBar(ts=2000, time="t2", open=1, high=1, low=1, close=1, volume_quote=1),
            FeatureBar(ts=3000, time="t3", open=1, high=1, low=1, close=1, volume_quote=1),
        ]
        rates = [
            FundingRate("BTC-USDT-SWAP", 1500, "f1", 0.0001, 0.0001),
            FundingRate("BTC-USDT-SWAP", 2500, "f2", -0.0002, -0.0002),
        ]

        enriched = add_funding_features(bars, rates)

        self.assertEqual(0.0, enriched[0].funding_rate)
        self.assertEqual(0.0001, enriched[1].funding_rate)
        self.assertEqual(-0.0002, enriched[2].funding_rate)
        self.assertAlmostEqual(-0.00005, enriched[2].funding_rate_ma)

    def test_download_funding_rates_merges_existing_cache_until_target_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            existing = [
                FundingRate("BTC-USDT-SWAP", 1_700_000_000_000, "old", 0.0001, 0.0001),
            ]
            save_funding_rates(out_dir / "BTC-USDT-SWAP_funding.csv", existing)
            page = [
                {
                    "instId": "BTC-USDT-SWAP",
                    "fundingRate": "0.0002",
                    "realizedRate": "0.0002",
                    "fundingTime": "1699971200000",
                },
                {
                    "instId": "BTC-USDT-SWAP",
                    "fundingRate": "0.0003",
                    "realizedRate": "0.0003",
                    "fundingTime": "1699942400000",
                },
            ]

            with patch("funding_rate.fetch_funding_page", return_value=page) as fetch:
                count = download_funding_rates(
                    "BTC-USDT-SWAP",
                    days=1,
                    out_dir=out_dir,
                    sleep_seconds=0.0,
                    limit=100,
                )

            self.assertEqual(3, count)
            fetch.assert_called_once_with(
                "BTC-USDT-SWAP",
                before=None,
                after=1_700_000_000_000,
                limit=100,
            )
            loaded = load_funding_rates(out_dir / "BTC-USDT-SWAP_funding.csv")
            self.assertEqual([1_699_942_400_000, 1_699_971_200_000, 1_700_000_000_000], [rate.ts for rate in loaded])

    def test_download_funding_rates_retries_transient_page_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            page = [
                {
                    "instId": "ETH-USDT-SWAP",
                    "fundingRate": "0.0002",
                    "realizedRate": "0.0002",
                    "fundingTime": "1700000000000",
                },
                {
                    "instId": "ETH-USDT-SWAP",
                    "fundingRate": "0.0001",
                    "realizedRate": "0.0001",
                    "fundingTime": "1699971200000",
                },
                {
                    "instId": "ETH-USDT-SWAP",
                    "fundingRate": "0.0001",
                    "realizedRate": "0.0001",
                    "fundingTime": "1699942400000",
                },
            ]

            with patch("funding_rate.fetch_funding_page", side_effect=[RuntimeError("busy"), page]) as fetch:
                count = download_funding_rates(
                    "ETH-USDT-SWAP",
                    days=1,
                    out_dir=out_dir,
                    sleep_seconds=0.0,
                    retry_sleep_seconds=0.0,
                    retries=1,
                    limit=100,
                )

            self.assertEqual(3, count)
            self.assertEqual(2, fetch.call_count)

    def test_main_downloads_requested_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            page = [
                {
                    "instId": "BTC-USDT-SWAP",
                    "fundingRate": "0.0002",
                    "realizedRate": "0.0002",
                    "fundingTime": "1700000000000",
                },
                {
                    "instId": "BTC-USDT-SWAP",
                    "fundingRate": "0.0001",
                    "realizedRate": "0.0001",
                    "fundingTime": "1699971200000",
                },
                {
                    "instId": "BTC-USDT-SWAP",
                    "fundingRate": "0.0001",
                    "realizedRate": "0.0001",
                    "fundingTime": "1699942400000",
                },
            ]

            with patch("funding_rate.fetch_funding_page", return_value=page):
                code = main([
                    "--symbols",
                    "BTC-USDT-SWAP",
                    "--days",
                    "1",
                    "--out",
                    str(out_dir),
                    "--sleep",
                    "0",
                ])

            self.assertEqual(0, code)
            loaded = load_funding_rates(out_dir / "BTC-USDT-SWAP_funding.csv")
            self.assertEqual(3, len(loaded))

    def test_main_returns_nonzero_for_incomplete_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            page = [{
                "instId": "BTC-USDT-SWAP",
                "fundingRate": "0.0002",
                "realizedRate": "0.0002",
                "fundingTime": "1700000000000",
            }]

            with patch("funding_rate.fetch_funding_page", return_value=page):
                code = main([
                    "--symbols", "BTC-USDT-SWAP", "--days", "1", "--out", str(out_dir), "--sleep", "0",
                ])

            self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
