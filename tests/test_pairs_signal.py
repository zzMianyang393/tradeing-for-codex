from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from config import BacktestConfig
from pairs_signal import PairsSignalGenerator


class TestPairsSignal(unittest.TestCase):
    def setUp(self) -> None:
        self.config = BacktestConfig(
            pairs_lookback_bars=10,
            pairs_entry_z=2.0,
            pairs_exit_z=0.0,
            pairs_max_hold_bars=10,
        )
        self.mock_fetcher = MagicMock()
        self.mock_storage = MagicMock()
        self.mock_fetcher.storage = self.mock_storage
        self.generator = PairsSignalGenerator(self.config, self.mock_fetcher)

    def test_get_latest_zscore_success(self):
        # Create aligned price series
        dates = pd.date_range("2026-01-01 00:00:00", periods=15, freq="15min")
        
        # Price A: A = 2 * B with some variation to prevent collinearity numerical instability
        prices_b = [50.0 + i for i in range(15)]
        prices_a = [2.0 * p for p in prices_b]
        prices_a[5] += 0.01  # Small variation
        
        df_a = pd.DataFrame({
            "symbol": ["A-USDT-SWAP"] * 15,
            "timeframe": ["15m"] * 15,
            "open": prices_a,
            "high": prices_a,
            "low": prices_a,
            "close": prices_a,
            "volume": [10.0] * 15,
        }, index=dates)
        
        df_b = pd.DataFrame({
            "symbol": ["B-USDT-SWAP"] * 15,
            "timeframe": ["15m"] * 15,
            "open": prices_b,
            "high": prices_b,
            "low": prices_b,
            "close": prices_b,
            "volume": [10.0] * 15,
        }, index=dates)

        self.mock_storage.load_klines.side_effect = lambda symbol, tf: df_a if symbol == "A-USDT-SWAP" else df_b

        res = self.generator.get_latest_zscore("A-USDT-SWAP", "B-USDT-SWAP", sync=True)

        self.mock_fetcher.sync_klines.assert_any_call("A-USDT-SWAP", "15m", days=90)
        self.mock_fetcher.sync_klines.assert_any_call("B-USDT-SWAP", "15m", days=90)

        self.assertEqual(res["timestamp"], dates[-1])
        self.assertEqual(res["price_a"], prices_a[-1])
        self.assertEqual(res["price_b"], prices_b[-1])
        # Relationship log(A) = 1.0 * log(B) + log(2.0)
        self.assertAlmostEqual(res["alpha"], np.log(2.0), places=2)
        self.assertAlmostEqual(res["beta"], 1.0, places=2)
        self.assertTrue(-1.0 < res["zscore"] < 1.0)

    def test_get_latest_zscore_insufficient_data(self):
        # Only 5 bars (lookback is 10)
        dates = pd.date_range("2026-01-01 00:00:00", periods=5, freq="15min")
        df_a = pd.DataFrame({"close": [100.0] * 5}, index=dates)
        df_b = pd.DataFrame({"close": [50.0] * 5}, index=dates)

        self.mock_storage.load_klines.side_effect = lambda symbol, tf: df_a if symbol == "A-USDT-SWAP" else df_b

        with self.assertRaises(ValueError) as ctx:
            self.generator.get_latest_zscore("A-USDT-SWAP", "B-USDT-SWAP", sync=False)
        self.assertIn("Insufficient data overlap", str(ctx.exception))

    def test_check_signal_triggers(self):
        # We will mock get_latest_zscore directly to return custom zscores
        with patch.object(self.generator, "get_latest_zscore") as mock_z:
            base_metrics = {
                "timestamp": pd.Timestamp("2026-01-01 00:00:00"),
                "price_a": 100.0,
                "price_b": 50.0,
                "beta": 1.0,
                "alpha": 0.0,
                "spread": 0.0,
            }

            # Case 1: Neutral, zscore is low -> hold
            mock_z.return_value = {**base_metrics, "zscore": 0.5}
            res = self.generator.check_signal("A", "B", current_position=0)
            self.assertEqual(res["signal"], "hold")

            # Case 2: Neutral, zscore is high -> entry_short
            mock_z.return_value = {**base_metrics, "zscore": 2.5}
            res = self.generator.check_signal("A", "B", current_position=0)
            self.assertEqual(res["signal"], "entry_short")

            # Case 3: Neutral, zscore is very low -> entry_long
            mock_z.return_value = {**base_metrics, "zscore": -2.5}
            res = self.generator.check_signal("A", "B", current_position=0)
            self.assertEqual(res["signal"], "entry_long")

            # Case 4: Long position, zscore goes to mean -> exit
            mock_z.return_value = {**base_metrics, "zscore": 0.1}
            res = self.generator.check_signal("A", "B", current_position=1)
            self.assertEqual(res["signal"], "exit")

            # Case 5: Short position, zscore spikes to stop_z -> exit
            mock_z.return_value = {**base_metrics, "zscore": 3.6}
            res = self.generator.check_signal("A", "B", current_position=-1)
            self.assertEqual(res["signal"], "exit")


if __name__ == "__main__":
    unittest.main()
