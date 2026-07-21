from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

from config import BacktestConfig
from data.fetcher import DataFetcher

logger = logging.getLogger("pairs_signal")


class PairsSignalGenerator:
    """Real-time pairs trading signal generator.

    Fetches price history, aligns K-lines, computes rolling OLS parameters, and
    calculates the latest Z-Score to identify entry/exit signals.
    """

    def __init__(self, config: BacktestConfig, fetcher: Optional[DataFetcher] = None) -> None:
        self.config = config
        self.fetcher = fetcher or DataFetcher()
        self.storage = self.fetcher.storage

    def get_latest_zscore(self, s1: str, s2: str, sync: bool = True) -> dict[str, Any]:
        """Synchronize prices, align timestamps, compute rolling OLS, and return latest Z-Score.

        Args:
            s1: Symbol of Asset A (e.g. 'FIL-USDT-SWAP').
            s2: Symbol of Asset B (e.g. 'OP-USDT-SWAP').
            sync: If True, synchronize recent K-lines from the exchange first.

        Returns:
            A dictionary containing timestamp, prices, beta, alpha, spread, and zscore.
        """
        # 1. Sync recent price data
        if sync:
            logger.info(f"Syncing K-lines for {s1} and {s2}...")
            try:
                # Sync 90 days to have enough lookback window data
                self.fetcher.sync_klines(s1, "15m", days=90)
                self.fetcher.sync_klines(s2, "15m", days=90)
            except Exception as e:
                logger.error(f"Error syncing K-lines during signal generation: {e}")

        # 2. Load K-lines from SQLite storage
        df1 = self.storage.load_klines(s1, "15m")
        df2 = self.storage.load_klines(s2, "15m")

        if df1.empty:
            raise ValueError(f"No price data found in database for {s1}")
        if df2.empty:
            raise ValueError(f"No price data found in database for {s2}")

        # 3. Inner join align timestamps
        df1_close = df1[["close"]].rename(columns={"close": s1})
        df2_close = df2[["close"]].rename(columns={"close": s2})
        df = df1_close.join(df2_close, how="inner")
        df.sort_index(inplace=True)

        # 4. Check data availability
        lookback = self.config.pairs_lookback_bars
        if len(df) < lookback + 1:
            raise ValueError(
                f"Insufficient data overlap ({len(df)} bars) for lookback ({lookback}) between {s1} and {s2}"
            )

        # Fit on completed history only.  The latest bar is the observation
        # being scored and must not influence the beta, mean or deviation used
        # to decide whether to trade it.
        df_slice = df.iloc[-(lookback + 1) : -1]
        latest = df.iloc[-1]
        y = np.log(df_slice[s1].values)
        x = np.log(df_slice[s2].values)

        X = sm.add_constant(x)
        model = sm.OLS(y, X).fit()
        alpha = model.params[0]
        beta = model.params[1]

        # Calculate historical spreads over this lookback window
        spreads = y - beta * x - alpha
        spread_mean = np.mean(spreads)
        spread_std = np.std(spreads)

        # Score the current completed bar with the prior-window model.
        latest_y = np.log(float(latest[s1]))
        latest_x = np.log(float(latest[s2]))
        latest_spread = latest_y - beta * latest_x - alpha
        latest_z = (latest_spread - spread_mean) / spread_std if spread_std > 0 else 0.0

        return {
            "timestamp": df.index[-1],
            "price_a": float(latest[s1]),
            "price_b": float(latest[s2]),
            "beta": float(beta),
            "alpha": float(alpha),
            "spread": float(latest_spread),
            "zscore": float(latest_z),
        }

    def check_signal(self, s1: str, s2: str, current_position: int = 0) -> dict[str, Any]:
        """Check entry and exit signal triggers based on Z-Score.

        Args:
            s1: Symbol of Asset A (e.g. 'FIL-USDT-SWAP').
            s2: Symbol of Asset B (e.g. 'OP-USDT-SWAP').
            current_position: Current position direction (0: neutral, 1: long A/short B, -1: short A/long B).

        Returns:
            A dictionary containing the latest metrics and a 'signal' value
            ('entry_long', 'entry_short', 'exit', or 'hold').
        """
        metrics = self.get_latest_zscore(s1, s2, sync=True)
        z = metrics["zscore"]

        entry_z = self.config.pairs_entry_z
        exit_z = self.config.pairs_exit_z
        stop_z = self.config.pairs_stop_z

        signal = "hold"

        if current_position == 0:
            # Check entry
            if z > entry_z and z < stop_z:
                signal = "entry_short"  # Short A, Long B
            elif z < -entry_z and z > -stop_z:
                signal = "entry_long"   # Long A, Short B
        else:
            # Check exit
            should_exit = False
            if abs(z) >= stop_z:
                should_exit = True
            elif current_position == 1 and z >= exit_z:
                should_exit = True
            elif current_position == -1 and z <= -exit_z:
                should_exit = True

            if should_exit:
                signal = "exit"

        result = dict(metrics)
        result["signal"] = signal
        return result
