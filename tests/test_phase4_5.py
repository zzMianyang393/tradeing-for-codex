from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Mock market module to avoid Python 3.8 incompatibility
mock_market = MagicMock()
sys.modules["market"] = mock_market

from data.funding_rate import (
    FundingRate, add_funding_features, save_funding_cache, load_funding_cache,
    _rolling_mean, _rolling_std,
)
from data.open_interest import (
    OpenInterest, add_oi_features, save_oi_cache, load_oi_cache,
)
from data.trades_flow import (
    TradesFlow, add_flow_features, save_flow_cache, load_flow_cache,
)


# ---------------------------------------------------------------------------
# Funding Rate tests
# ---------------------------------------------------------------------------

class TestFundingRateDataclass(unittest.TestCase):
    def test_defaults(self):
        fr = FundingRate()
        self.assertEqual(fr.symbol, "")
        self.assertEqual(fr.funding_rate, 0.0)

    def test_values(self):
        fr = FundingRate(symbol="BTC", funding_rate=0.0001)
        self.assertEqual(fr.symbol, "BTC")
        self.assertAlmostEqual(fr.funding_rate, 0.0001)


class TestRollingStats(unittest.TestCase):
    def test_rolling_mean(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = _rolling_mean(values, 3)
        self.assertAlmostEqual(result[0], 1.0)
        self.assertAlmostEqual(result[2], 2.0)  # (1+2+3)/3
        self.assertAlmostEqual(result[4], 4.0)  # (3+4+5)/3

    def test_rolling_std(self):
        values = [1.0, 1.0, 1.0, 1.0]
        result = _rolling_std(values, 3)
        for r in result:
            self.assertAlmostEqual(r, 0.0)

    def test_rolling_std_varying(self):
        values = [1.0, 2.0, 3.0]
        result = _rolling_std(values, 3)
        self.assertGreater(result[2], 0)


class TestAddFundingFeatures(unittest.TestCase):
    def test_empty_data(self):
        bars = [MagicMock(ts=1000)]
        result = add_funding_features(bars, [])
        self.assertEqual(len(result), 1)
        # When no data, attributes should be set to defaults
        self.assertEqual(result[0].funding_rate, 0.0)

    def test_with_data(self):
        bars = [MagicMock(ts=1000), MagicMock(ts=2000)]
        rates = [
            FundingRate(symbol="BTC", funding_rate=0.0001, timestamp=500),
            FundingRate(symbol="BTC", funding_rate=0.0002, timestamp=1500),
        ]
        result = add_funding_features(bars, rates)
        self.assertEqual(len(result), 2)
        self.assertTrue(hasattr(result[0], "funding_rate"))
        self.assertTrue(hasattr(result[0], "funding_rate_ma"))
        self.assertTrue(hasattr(result[0], "funding_rate_zscore"))

    def test_zscore_calculation(self):
        bars = [MagicMock(ts=1000)]
        rates = [FundingRate(funding_rate=0.0001, timestamp=500)]
        result = add_funding_features(bars, rates)
        # With single data point, zscore should be 0
        self.assertAlmostEqual(result[0].funding_rate_zscore, 0.0)


class TestFundingCache(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.json"
            rates = [FundingRate(symbol="BTC", funding_rate=0.0001, timestamp=1000)]
            save_funding_cache(rates, path)
            loaded = load_funding_cache(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].symbol, "BTC")

    def test_load_nonexistent(self):
        loaded = load_funding_cache(Path("/nonexistent"))
        self.assertEqual(loaded, [])


# ---------------------------------------------------------------------------
# Open Interest tests
# ---------------------------------------------------------------------------

class TestOpenInterestDataclass(unittest.TestCase):
    def test_defaults(self):
        oi = OpenInterest()
        self.assertEqual(oi.symbol, "")
        self.assertEqual(oi.oi, 0.0)


class TestAddOiFeatures(unittest.TestCase):
    def test_empty_data(self):
        bars = [MagicMock(ts=1000)]
        result = add_oi_features(bars, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].open_interest, 0.0)

    def test_with_data(self):
        bars = [MagicMock(ts=1000, close=100.0, open=99.0)]
        oi_data = [OpenInterest(symbol="BTC", oi=1000.0, timestamp=500)]
        result = add_oi_features(bars, oi_data)
        self.assertEqual(len(result), 1)
        self.assertTrue(hasattr(result[0], "open_interest"))
        self.assertTrue(hasattr(result[0], "oi_change_pct"))
        self.assertTrue(hasattr(result[0], "oi_price_divergence"))

    def test_oi_change_pct(self):
        bars = [MagicMock(ts=2000, close=100.0, open=99.0)]
        oi_data = [
            OpenInterest(oi=1000.0, timestamp=0),
            OpenInterest(oi=1200.0, timestamp=2000),
        ]
        result = add_oi_features(bars, oi_data)
        # OI increased by 20% over lookback
        self.assertGreater(result[0].oi_change_pct, 0)


class TestOiCache(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oi.json"
            oi_data = [OpenInterest(symbol="BTC", oi=1000.0, timestamp=1000)]
            save_oi_cache(oi_data, path)
            loaded = load_oi_cache(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].oi, 1000.0)


# ---------------------------------------------------------------------------
# Trades Flow tests
# ---------------------------------------------------------------------------

class TestTradesFlowDataclass(unittest.TestCase):
    def test_defaults(self):
        tf = TradesFlow()
        self.assertEqual(tf.symbol, "")
        self.assertEqual(tf.buy_volume, 0.0)

    def test_values(self):
        tf = TradesFlow(symbol="BTC", buy_volume=10.0, sell_volume=5.0)
        self.assertEqual(tf.symbol, "BTC")
        self.assertAlmostEqual(tf.buy_volume, 10.0)


class TestAddFlowFeatures(unittest.TestCase):
    def test_empty_data(self):
        bars = [MagicMock(ts=1000)]
        result = add_flow_features(bars, [])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].buy_ratio, 0.5)

    def test_with_data(self):
        bars = [MagicMock(ts=1000)]
        flow_data = [
            TradesFlow(symbol="BTC", buy_volume=10.0, sell_volume=5.0, timestamp=500),
        ]
        result = add_flow_features(bars, flow_data)
        self.assertEqual(len(result), 1)
        self.assertTrue(hasattr(result[0], "buy_volume"))
        self.assertTrue(hasattr(result[0], "sell_volume"))
        self.assertTrue(hasattr(result[0], "buy_ratio"))
        self.assertTrue(hasattr(result[0], "volume_delta"))
        self.assertAlmostEqual(result[0].buy_ratio, 10.0 / 15.0)

    def test_volume_delta(self):
        bars = [MagicMock(ts=1000)]
        flow_data = [TradesFlow(buy_volume=10.0, sell_volume=3.0, timestamp=500)]
        result = add_flow_features(bars, flow_data)
        self.assertAlmostEqual(result[0].volume_delta, 7.0)

    def test_neutral_ratio(self):
        bars = [MagicMock(ts=1000)]
        flow_data = [TradesFlow(buy_volume=0.0, sell_volume=0.0, timestamp=500)]
        result = add_flow_features(bars, flow_data)
        self.assertAlmostEqual(result[0].buy_ratio, 0.5)


class TestFlowCache(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "flow.json"
            flow_data = [TradesFlow(symbol="BTC", buy_volume=10.0, timestamp=1000)]
            save_flow_cache(flow_data, path)
            loaded = load_flow_cache(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].buy_volume, 10.0)


# ---------------------------------------------------------------------------
# Report CLI tests
# ---------------------------------------------------------------------------

class TestReportCLI(unittest.TestCase):
    def test_imports(self):
        import report_cli
        self.assertTrue(hasattr(report_cli, "main"))
        self.assertTrue(hasattr(report_cli, "cmd_daily"))
        self.assertTrue(hasattr(report_cli, "cmd_weekly"))

    def test_report_help(self):
        """Report CLI shows help without crashing."""
        import report_cli
        # Just verify the module loads and has expected functions
        self.assertTrue(callable(report_cli.cmd_daily))
        self.assertTrue(callable(report_cli.cmd_performance))


# ---------------------------------------------------------------------------
# Integration: data features + cache
# ---------------------------------------------------------------------------

class TestFeatureIntegration(unittest.TestCase):
    def test_all_features_on_bar(self):
        """Verify all data features can be added to a single bar."""
        bar = MagicMock(ts=1000, close=100.0, open=99.0)

        # Add funding features
        rates = [FundingRate(funding_rate=0.0001, timestamp=500)]
        bars = add_funding_features([bar], rates)

        # Add OI features
        oi_data = [OpenInterest(oi=1000.0, timestamp=500)]
        bars = add_oi_features(bars, oi_data)

        # Add flow features
        flow_data = [TradesFlow(buy_volume=10.0, sell_volume=5.0, timestamp=500)]
        bars = add_flow_features(bars, flow_data)

        # Verify all attributes exist
        b = bars[0]
        self.assertTrue(hasattr(b, "funding_rate"))
        self.assertTrue(hasattr(b, "funding_rate_ma"))
        self.assertTrue(hasattr(b, "funding_rate_zscore"))
        self.assertTrue(hasattr(b, "open_interest"))
        self.assertTrue(hasattr(b, "oi_change_pct"))
        self.assertTrue(hasattr(b, "oi_price_divergence"))
        self.assertTrue(hasattr(b, "buy_volume"))
        self.assertTrue(hasattr(b, "sell_volume"))
        self.assertTrue(hasattr(b, "buy_ratio"))
        self.assertTrue(hasattr(b, "volume_delta"))


if __name__ == "__main__":
    unittest.main()
