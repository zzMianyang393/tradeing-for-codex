import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import pandas as pd
import numpy as np

from config import BacktestConfig
from pairs_backtester import PairsBacktester


class PairsBacktesterTests(unittest.TestCase):
    def setUp(self):
        self.config = BacktestConfig(
            pairs_lookback_bars=10,
            pairs_entry_z=1.0,
            pairs_exit_z=0.0,
            pairs_max_hold_bars=5,
            taker_fee=0.0005,
            slippage=0.0002,
            start_equity=10.0
        )
        self.tester = PairsBacktester(self.config)

    @patch("pandas.read_csv")
    def test_load_and_align_prices(self, mock_read_csv):
        # Create mock dataframes
        df1 = pd.DataFrame({
            "timestamp": ["2026-01-01 00:00:00", "2026-01-01 00:15:00", "2026-01-01 00:30:00"],
            "close": [10.0, 11.0, 12.0]
        })
        df2 = pd.DataFrame({
            "timestamp": ["2026-01-01 00:00:00", "2026-01-01 00:15:00", "2026-01-01 00:45:00"],
            "close": [100.0, 105.0, 110.0]
        })

        mock_read_csv.side_effect = [df1, df2]

        data_dir = Path("mock_data_dir")
        with patch.object(Path, "exists", return_value=True):
            df_aligned = self.tester.load_and_align_prices("A", "B", data_dir)

        # Verify alignment via inner join (only overlapping dates)
        self.assertEqual(2, len(df_aligned))
        self.assertIn("A", df_aligned.columns)
        self.assertIn("B", df_aligned.columns)
        self.assertEqual(10.0, df_aligned.loc["2026-01-01 00:00:00", "A"])
        self.assertEqual(105.0, df_aligned.loc["2026-01-01 00:15:00", "B"])

    def test_calculate_indicators(self):
        # Generate clean cointegrated series
        np.random.seed(42)
        n = 50
        x = np.linspace(1, 10, n)
        # y = 2 * x + const + noise
        y = 2.0 * x + 5.0 + np.random.normal(0, 0.1, n)

        dates = pd.date_range("2026-01-01 00:00:00", periods=n, freq="15min")
        df = pd.DataFrame({"A": np.exp(y), "B": np.exp(x)}, index=dates)

        df_indicators = self.tester.calculate_indicators("A", "B", df)

        self.assertIn("spread", df_indicators.columns)
        self.assertIn("zscore", df_indicators.columns)
        self.assertIn("beta", df_indicators.columns)
        # The length should be n - lookback (50 - 10 = 40)
        self.assertEqual(40, len(df_indicators))

    def test_run_trading_simulation_enters_and_exits(self):
        # Create a simple dataframe where z-score crosses threshold and reverts
        dates = pd.date_range("2026-01-01 00:00:00", periods=20, freq="15min")
        
        # Prices
        a = [100.0] * 20
        b = [100.0] * 20
        # Make a wide spread at index 5 (A goes up, B goes down) -> zscore goes positive
        a[5] = 110.0
        b[5] = 90.0
        # Revert back at index 7
        
        df = pd.DataFrame({"A": a, "B": b}, index=dates)
        # Populate pre-calculated indicators to mock indicator step
        z_vals = [0.0] * 20
        z_vals[5] = 2.5 # Trigger entry: z > 1.0 (since config.pairs_entry_z = 1.0)
        z_vals[6] = 1.5
        z_vals[7] = -0.1 # Trigger exit: z <= 0.0
        df["zscore"] = z_vals
        df["beta"] = 1.0

        res = self.tester.run_trading_simulation("A", "B", df)
        
        self.assertEqual(1, res["trades"])
        self.assertEqual(1, len(res["trades_detail"]))
        
        trade = res["trades_detail"][0]
        self.assertEqual("short_s1_long_s2", trade["direction"]) # Since z > 1.0 is short s1/long s2
        self.assertEqual(2, trade["duration_bars"]) # Signal at 5 enters at 6 open; signal at 7 exits at 8 open.
        self.assertEqual("mean_reversion", trade["exit_reason"])

    def test_run_trading_simulation_hits_max_hold(self):
        # Create a simple dataframe where z-score triggers entry but never reverts
        dates = pd.date_range("2026-01-01 00:00:00", periods=20, freq="15min")
        
        a = [100.0] * 20
        b = [100.0] * 20
        df = pd.DataFrame({"A": a, "B": b}, index=dates)
        
        z_vals = [0.0] * 20
        z_vals[2] = 2.5 # Entry
        # Stays wide but below entry threshold
        for idx in range(3, 20):
            z_vals[idx] = 0.5
        df["zscore"] = z_vals
        df["beta"] = 1.0

        res = self.tester.run_trading_simulation("A", "B", df)
        
        self.assertEqual(1, res["trades"])
        trade = res["trades_detail"][0]
        # A time-stop signal at five held bars executes on the next bar's open.
        self.assertEqual(6, trade["duration_bars"])
        self.assertEqual("time_stop", trade["exit_reason"])


    def test_portfolio_concurrent_execution(self):
        dates = pd.date_range("2026-01-01 00:00:00", periods=20, freq="15min")
        
        # Pair 1: A-B
        df_ab = pd.DataFrame({"A": [100.0] * 20, "B": [100.0] * 20}, index=dates)
        z_ab = [0.0] * 20
        z_ab[2] = 2.5 # Entry for A-B
        z_ab[4] = -0.1 # Exit for A-B
        df_ab["zscore"] = z_ab
        
        # Pair 2: C-D
        df_cd = pd.DataFrame({"C": [10.0] * 20, "D": [10.0] * 20}, index=dates)
        z_cd = [0.0] * 20
        z_cd[3] = 2.5 # Entry for C-D
        z_cd[5] = -0.1 # Exit for C-D
        df_cd["zscore"] = z_cd
        
        pair_dfs = {"A-B": df_ab, "C-D": df_cd}
        res = self.tester.run_portfolio_simulation(pair_dfs)
        
        self.assertEqual(2, res["trades"])
        self.assertEqual(2, len(res["trades_detail"]))
        
        # Check directions/pairs
        pairs_traded = [t["pair"] for t in res["trades_detail"]]
        self.assertIn("A-B", pairs_traded)
        self.assertIn("C-D", pairs_traded)

    def test_portfolio_allocation_limits(self):
        dates = pd.date_range("2026-01-01 00:00:00", periods=20, freq="15min")
        
        # Limit to max 2 active pairs
        self.tester.config = BacktestConfig(
            pairs_lookback_bars=10,
            pairs_entry_z=1.0,
            pairs_exit_z=0.0,
            pairs_max_active=2,
            taker_fee=0.0005,
            slippage=0.0002
        )
        
        pair_dfs = {}
        for p in ["A-B", "C-D", "E-F"]:
            s1, s2 = p.split("-")
            df = pd.DataFrame({s1: [100.0] * 20, s2: [100.0] * 20}, index=dates)
            z = [0.0] * 20
            z[2] = 2.5 # All trigger at same time step
            df["zscore"] = z
            pair_dfs[p] = df
            
        res = self.tester.run_portfolio_simulation(pair_dfs)
        
        # Only 2 pairs should have entered since max_active is 2
        # (They will remain open because there is no exit trigger and they don't hit max_hold in 20 bars, wait, max_hold is 200 by default. So they won't exit, and total trades realized in trades_detail will be 0 because they are not closed yet).
        # Wait! To verify how many entered, let's trigger exits for all at index 5 so they close and show up in trades_detail.
        for p in pair_dfs:
            z_vals = list(pair_dfs[p]["zscore"])
            z_vals[5] = -0.1
            pair_dfs[p]["zscore"] = z_vals
            
        res = self.tester.run_portfolio_simulation(pair_dfs)
        self.assertEqual(2, res["trades"]) # Only 2 trades closed (and only 2 entered)

    def test_portfolio_stop_z_loss(self):
        dates = pd.date_range("2026-01-01 00:00:00", periods=20, freq="15min")
        
        df = pd.DataFrame({"A": [100.0] * 20, "B": [100.0] * 20}, index=dates)
        z = [0.0] * 20
        z[2] = 2.5 # Entry
        z[3] = 2.5 # Stays wide
        z[4] = 3.6 # Exceeds pairs_stop_z (3.5)
        df["zscore"] = z
        
        pair_dfs = {"A-B": df}
        res = self.tester.run_portfolio_simulation(pair_dfs)
        
        self.assertEqual(1, res["trades"])
        trade = res["trades_detail"][0]
        self.assertEqual("stop_loss", trade["exit_reason"])
        self.assertEqual(2, trade["duration_bars"])


if __name__ == "__main__":
    unittest.main()
