from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

from config import BacktestConfig

logger = logging.getLogger("pairs_backtester")


class PairsBacktester:
    """Dedicated backtester for statistical arbitrage pairs trading.

    Supports both single-pair backtests and concurrent multi-pair portfolio backtests.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config

    def load_and_align_prices(self, s1: str, s2: str, data_dir: Path) -> pd.DataFrame:
        """Load 15m CSVs for s1 and s2 and align them by timestamp."""
        s1_clean = s1.split("-")[0]
        s2_clean = s2.split("-")[0]
        
        file1 = data_dir / f"{s1_clean}_15m.csv"
        file2 = data_dir / f"{s2_clean}_15m.csv"
        
        if not file1.exists():
            file1 = data_dir / f"{s1}_15m.csv"
        if not file2.exists():
            file2 = data_dir / f"{s2}_15m.csv"
            
        if not file1.exists() or not file2.exists():
            raise FileNotFoundError(f"Could not find 15m CSV files for {s1} ({file1}) or {s2} ({file2})")

        df1 = pd.read_csv(file1, usecols=lambda column: column in {"timestamp", "open", "close"})
        if "open" not in df1:
            df1["open"] = df1["close"]
        df1["timestamp"] = pd.to_datetime(df1["timestamp"])
        df1.set_index("timestamp", inplace=True)
        df1.rename(columns={"open": f"{s1}_open", "close": s1}, inplace=True)

        df2 = pd.read_csv(file2, usecols=lambda column: column in {"timestamp", "open", "close"})
        if "open" not in df2:
            df2["open"] = df2["close"]
        df2["timestamp"] = pd.to_datetime(df2["timestamp"])
        df2.set_index("timestamp", inplace=True)
        df2.rename(columns={"open": f"{s2}_open", "close": s2}, inplace=True)

        df = df1.join(df2, how="inner")
        df.sort_index(inplace=True)
        return df

    def calculate_indicators(self, s1: str, s2: str, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate rolling OLS spread, beta, and z-score on aligned prices."""
        lookback = self.config.pairs_lookback_bars
        if len(df) < lookback + 10:
            raise ValueError(f"Insufficient data overlap ({len(df)} rows) for lookback ({lookback})")

        y = np.log(df[s1].values)
        x = np.log(df[s2].values)

        df = df.copy()
        x_series = pd.Series(x, index=df.index)
        y_series = pd.Series(y, index=df.index)
        # Every model at t is fit solely on [t-lookback, t).  The current
        # close only produces a signal and must be executed no earlier than
        # the next bar's open.
        prior_x = x_series.shift(1)
        prior_y = y_series.shift(1)
        mean_x = prior_x.rolling(lookback, min_periods=lookback).mean()
        mean_y = prior_y.rolling(lookback, min_periods=lookback).mean()
        mean_xx = (prior_x * prior_x).rolling(lookback, min_periods=lookback).mean()
        mean_xy = (prior_x * prior_y).rolling(lookback, min_periods=lookback).mean()
        mean_yy = (prior_y * prior_y).rolling(lookback, min_periods=lookback).mean()
        var_x = mean_xx - mean_x * mean_x
        beta = (mean_xy - mean_x * mean_y) / var_x.where(var_x.abs() > 1e-12)
        alpha = mean_y - beta * mean_x
        spread = y_series - alpha - beta * x_series
        residual_variance = (
            mean_yy - 2.0 * alpha * mean_y - 2.0 * beta * mean_xy
            + alpha * alpha + 2.0 * alpha * beta * mean_x + beta * beta * mean_xx
        ).clip(lower=0.0)
        spread_std = np.sqrt(residual_variance)
        df["spread"] = spread
        df["beta"] = beta
        df["alpha"] = alpha
        df["spread_mean"] = 0.0
        df["spread_std"] = spread_std
        df["zscore"] = spread / spread_std.where(spread_std > 1e-12)
        df.dropna(subset=["zscore", "beta", "alpha"], inplace=True)
        return df

    def run_trading_simulation(
        self, s1: str, s2: str, df: pd.DataFrame, window_bars: int | None = None
    ) -> dict[str, Any]:
        """Simulate pairs trading execution for a single pair."""
        if window_bars is not None:
            df_slice = df.iloc[-window_bars:]
        else:
            df_slice = df

        if len(df_slice) == 0:
            return {
                "trades": 0,
                "net_profit_pct": 0.0,
                "win_rate": 0.0,
                "avg_pnl_pct": 0.0,
                "trades_detail": []
            }

        zscores = df_slice["zscore"].values
        y_prices = df_slice[s1].values
        x_prices = df_slice[s2].values
        y_opens = df_slice.get(f"{s1}_open", df_slice[s1]).values
        x_opens = df_slice.get(f"{s2}_open", df_slice[s2]).values
        betas = df_slice["beta"].values
        times = df_slice.index.astype(str).values

        entry_z = self.config.pairs_entry_z
        exit_z = self.config.pairs_exit_z
        stop_z = self.config.pairs_stop_z
        max_hold = self.config.pairs_max_hold_bars

        equity = self.config.start_equity
        initial_equity = equity
        fee = self.config.taker_fee
        slippage = self.config.slippage
        cost_rate = fee + slippage

        position: dict[str, Any] | None = None
        pending_entry: tuple[int, int] | None = None
        pending_exit: str | None = None

        trades = []

        def close_position(pos: dict[str, Any], y_p: float, x_p: float, time_str: str, reason: str) -> None:
            nonlocal equity
            if pos["direction"] == 1:
                gross = (y_p - pos["entry_y"]) * pos["qty_y"] + (pos["entry_x"] - x_p) * pos["qty_x"]
            else:
                gross = (pos["entry_y"] - y_p) * pos["qty_y"] + (x_p - pos["entry_x"]) * pos["qty_x"]
            exit_cost = (pos["qty_y"] * y_p + pos["qty_x"] * x_p) * cost_rate
            before = equity
            net_pnl = gross - exit_cost
            equity += net_pnl
            trades.append({
                "entry_time": pos["entry_time"], "exit_time": time_str,
                "direction": "long_s1_short_s2" if pos["direction"] == 1 else "short_s1_long_s2",
                "beta": round(pos["beta"], 6), "pnl": round(net_pnl, 6),
                "pnl_pct": round(net_pnl / before * 100.0, 4) if before > 0 else 0.0,
                "duration_bars": pos["entry_idx"] and t - pos["entry_idx"], "exit_reason": reason,
            })

        for t in range(1, len(df_slice)):
            z = zscores[t]
            y_p = y_opens[t]
            x_p = x_opens[t]
            time_str = times[t]

            if pending_exit is not None and position is not None:
                close_position(position, y_p, x_p, time_str, pending_exit)
                position = None
                pending_exit = None
            if pending_entry is not None and position is None:
                direction, signal_idx = pending_entry
                beta = abs(float(betas[signal_idx]))
                gross_notional = equity
                y_notional = gross_notional / (1.0 + beta)
                x_notional = gross_notional - y_notional
                entry_cost = gross_notional * cost_rate
                equity -= entry_cost
                position = {
                    "direction": direction, "entry_idx": t, "entry_time": time_str,
                    "entry_y": y_p, "entry_x": x_p, "qty_y": y_notional / y_p,
                    "qty_x": x_notional / x_p, "beta": beta,
                }
                pending_entry = None

            # At this close we only schedule an order for the next bar's open.
            if position is None:
                if z > entry_z:
                    pending_entry = (-1, t)
                elif z < -entry_z:
                    pending_entry = (1, t)
            elif pending_exit is None:
                held = t - position["entry_idx"]
                if abs(z) >= stop_z:
                    pending_exit = "stop_loss"
                elif position["direction"] == 1 and z >= exit_z:
                    pending_exit = "mean_reversion"
                elif position["direction"] == -1 and z <= -exit_z:
                    pending_exit = "mean_reversion"
                elif held >= max_hold:
                    pending_exit = "time_stop"

        if position is not None:
            # A validation window must not leave an uncharged synthetic leg open.
            close_position(position, y_prices[-1], x_prices[-1], times[-1], "end_of_test")

        total_trades = len(trades)
        if total_trades == 0:
            return {
                "trades": 0,
                "net_profit_pct": 0.0,
                "win_rate": 0.0,
                "avg_pnl_pct": 0.0,
                "trades_detail": []
            }

        wins = sum(1 for tr in trades if tr["pnl"] > 0)
        win_rate = (wins / total_trades) * 100.0
        net_profit_pct = ((equity - initial_equity) / initial_equity) * 100.0
        avg_pnl_pct = sum(tr["pnl_pct"] for tr in trades) / total_trades

        return {
            "trades": total_trades,
            "net_profit_pct": round(net_profit_pct, 2),
            "win_rate": round(win_rate, 1),
            "avg_pnl_pct": round(avg_pnl_pct, 4),
            "trades_detail": trades
        }

    def run_portfolio_simulation(
        self, pair_dfs: dict[str, pd.DataFrame], window_bars: int | None = None
    ) -> dict[str, Any]:
        """Simulate concurrent pairs trading portfolio backtest."""
        # Find unified timestamps index
        all_timestamps = sorted(set().union(*(df.index for df in pair_dfs.values())))
        if not all_timestamps:
            return {}

        if window_bars is not None:
            all_timestamps = all_timestamps[-window_bars:]

        # Portfolio accounting state
        start_equity = self.config.start_equity
        cash = start_equity
        active_positions: dict[str, dict[str, Any]] = {}
        
        trades_detail = []
        equity_curve = []
        
        fee = self.config.taker_fee
        slippage = self.config.slippage
        cost_rate = fee + slippage
        
        max_active = self.config.pairs_max_active
        allocation_fraction = self.config.pairs_allocation_fraction
        entry_z = self.config.pairs_entry_z
        exit_z = self.config.pairs_exit_z
        stop_z = self.config.pairs_stop_z
        max_hold = self.config.pairs_max_hold_bars

        # Fast lookup cache for price data inside loop
        # pair_key -> dataframe columns
        cache: dict[str, dict[str, Any]] = {}
        for pair_key, df in pair_dfs.items():
            s1, s2 = pair_key.split("-")
            cache[pair_key] = {
                "zscores": df["zscore"].to_dict(),
                "y_prices": df[s1].to_dict(),
                "x_prices": df[s2].to_dict(),
            }

        for idx, ts in enumerate(all_timestamps):
            # 1. Calculate current mark-to-market open PnL to update equity
            open_pnl = 0.0
            for pair_key, pos in list(active_positions.items()):
                # Get current prices at ts
                pair_cache = cache[pair_key]
                if ts not in pair_cache["y_prices"] or ts not in pair_cache["x_prices"]:
                    # Keep open PnL flat if data missing for this bar
                    continue
                y_p = pair_cache["y_prices"][ts]
                x_p = pair_cache["x_prices"][ts]
                
                direction = pos["direction"]
                qty_y = pos["qty_y"]
                qty_x = pos["qty_x"]
                
                if direction == 1:
                    pnl_y = (y_p - pos["entry_y"]) * qty_y
                    pnl_x = (pos["entry_x"] - x_p) * qty_x
                else:
                    pnl_y = (pos["entry_y"] - y_p) * qty_y
                    pnl_x = (x_p - pos["entry_x"]) * qty_x
                open_pnl += (pnl_y + pnl_x)
                
            current_equity = cash + open_pnl
            
            # Record daily/weekly equity curve (downsample or record at interval)
            # Record every 96 bars (daily) or final bar
            if idx % 96 == 0 or idx == len(all_timestamps) - 1:
                equity_curve.append((str(ts), round(current_equity, 4)))

            # 2. Check exits
            for pair_key, pos in list(active_positions.items()):
                pair_cache = cache[pair_key]
                if ts not in pair_cache["zscores"]:
                    continue
                z = pair_cache["zscores"][ts]
                y_p = pair_cache["y_prices"][ts]
                x_p = pair_cache["x_prices"][ts]
                
                time_held = idx - pos["entry_idx"]
                should_exit = False
                exit_reason = "mean_reversion"
                direction = pos["direction"]

                # Check stop loss
                if abs(z) >= stop_z:
                    should_exit = True
                    exit_reason = "stop_loss"
                elif direction == 1 and (z >= exit_z or time_held >= max_hold):
                    should_exit = True
                    if time_held >= max_hold:
                        exit_reason = "time_stop"
                elif direction == -1 and (z <= -exit_z or time_held >= max_hold):
                    should_exit = True
                    if time_held >= max_hold:
                        exit_reason = "time_stop"

                if should_exit:
                    # Realize PnL
                    qty_y = pos["qty_y"]
                    qty_x = pos["qty_x"]
                    
                    if direction == 1:
                        pnl_y = (y_p - pos["entry_y"]) * qty_y
                        pnl_x = (pos["entry_x"] - x_p) * qty_x
                    else:
                        pnl_y = (pos["entry_y"] - y_p) * qty_y
                        pnl_x = (x_p - pos["entry_x"]) * qty_x
                        
                    exit_cost = (qty_y * y_p + qty_x * x_p) * cost_rate
                    net_realized = pnl_y + pnl_x - exit_cost
                    cash += net_realized
                    
                    trades_detail.append({
                        "pair": pair_key,
                        "entry_time": pos["entry_time"],
                        "exit_time": str(ts),
                        "direction": "long_s1_short_s2" if direction == 1 else "short_s1_long_s2",
                        "pnl": round(net_realized, 6),
                        "pnl_pct": round((net_realized / pos["equity_at_entry"]) * 100.0, 4),
                        "duration_bars": time_held,
                        "exit_reason": exit_reason
                    })
                    
                    del active_positions[pair_key]

            # Re-calculate current equity after exits
            current_equity = cash + sum(
                (qty_y * (y_p - pos["entry_y"]) + qty_x * (pos["entry_x"] - x_p)) if pos["direction"] == 1
                else (qty_y * (pos["entry_y"] - y_p) + qty_x * (x_p - pos["entry_x"]))
                for pair_key, pos in active_positions.items()
                for y_p, x_p in [(cache[pair_key]["y_prices"].get(ts, pos["entry_y"]), cache[pair_key]["x_prices"].get(ts, pos["entry_x"]))]
                for qty_y, qty_x in [(pos["qty_y"], pos["qty_x"])]
            )

            # 3. Check entries
            # Find eligible triggers
            triggers = []
            for pair_key, pair_cache in cache.items():
                if pair_key in active_positions:
                    continue
                if ts not in pair_cache["zscores"] or ts not in pair_cache["y_prices"] or ts not in pair_cache["x_prices"]:
                    continue
                
                z = pair_cache["zscores"][ts]
                if abs(z) >= entry_z and abs(z) < stop_z:
                    # Record Z-Score for priority sorting
                    triggers.append((pair_key, z, pair_cache["y_prices"][ts], pair_cache["x_prices"][ts]))

            # Sort triggers by |z| descending (widest spread first)
            triggers.sort(key=lambda item: abs(item[1]), reverse=True)

            for pair_key, z, y_p, x_p in triggers:
                if len(active_positions) >= max_active:
                    break
                
                # Sizing based on current portfolio equity
                notional = current_equity * allocation_fraction
                qty_y = notional / y_p
                qty_x = notional / x_p
                
                direction = 1 if z < 0 else -1
                
                # Pay entry fee
                entry_cost = 2.0 * notional * cost_rate
                cash -= entry_cost
                
                active_positions[pair_key] = {
                    "entry_time": str(ts),
                    "entry_idx": idx,
                    "entry_y": y_p,
                    "entry_x": x_p,
                    "qty_y": qty_y,
                    "qty_x": qty_x,
                    "direction": direction,
                    "equity_at_entry": current_equity,
                }

        # Calculate final metrics
        total_trades = len(trades_detail)
        net_profit_pct = ((current_equity - start_equity) / start_equity) * 100.0
        
        wins = sum(1 for tr in trades_detail if tr["pnl"] > 0)
        win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
        avg_pnl_pct = sum(tr["pnl_pct"] for tr in trades_detail) / total_trades if total_trades > 0 else 0.0

        # Calculate Max Drawdown and Sharpe Ratio from daily equity curve
        df_eq = pd.DataFrame(equity_curve, columns=["date", "equity"])
        df_eq["equity_prev"] = df_eq["equity"].shift(1)
        df_eq["daily_return"] = (df_eq["equity"] - df_eq["equity_prev"]) / df_eq["equity_prev"]
        
        # Sharpe ratio
        daily_mean = df_eq["daily_return"].mean()
        daily_std = df_eq["daily_return"].std()
        sharpe = np.sqrt(365) * (daily_mean / daily_std) if daily_std > 0 else 0.0
        
        # Max drawdown
        df_eq["peak"] = df_eq["equity"].cummax()
        df_eq["drawdown"] = (df_eq["peak"] - df_eq["equity"]) / df_eq["peak"]
        max_dd = df_eq["drawdown"].max() * 100.0

        return {
            "trades": total_trades,
            "net_profit_pct": round(net_profit_pct, 2),
            "win_rate": round(win_rate, 1),
            "avg_pnl_pct": round(avg_pnl_pct, 4),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "equity_curve": equity_curve,
            "trades_detail": trades_detail
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pairs trading backtester.")
    parser.add_argument("--data", type=Path, default=Path("data"), help="Directory containing CSV market data.")
    parser.add_argument("--pairs", required=True, help="Comma-separated pairs list, e.g. FIL-OP,ARB-AVAX.")
    parser.add_argument("--windows", default="90,180,365", help="Comma-separated list of window sizes in days.")
    parser.add_argument("--mode", default="individual", choices=["individual", "portfolio"], help="Backtest mode; portfolio is retained only for legacy diagnostics.")
    parser.add_argument("--out", type=Path, default=Path("reports/pairs_validation.json"), help="Output path for JSON report.")
    args = parser.parse_args()

    if args.mode == "portfolio":
        print("ERROR: portfolio mode uses legacy accounting and is disabled for validation; use pairs_walk_forward.py.")
        return 2

    config = BacktestConfig()
    tester = PairsBacktester(config)

    # Parse pairs list
    pair_list = []
    for item in args.pairs.split(","):
        if not item.strip():
            continue
        parts = item.split("-")
        if len(parts) < 2:
            print(f"Invalid pair format: {item}. Expected A-B.")
            return 1
        pair_list.append((parts[0].strip(), parts[1].strip()))

    # Parse windows
    try:
        windows = [int(w.strip()) for w in args.windows.split(",") if w.strip()]
    except ValueError:
        print("--windows must contain comma-separated integers.")
        return 1

    # Load and pre-calculate all pairs
    pair_dfs = {}
    for s1, s2 in pair_list:
        pair_key = f"{s1}-{s2}"
        try:
            df = tester.load_and_align_prices(s1, s2, args.data)
            df = tester.calculate_indicators(s1, s2, df)
            pair_dfs[pair_key] = df
            print(f"Precalculated indicators for {pair_key} successfully.")
        except Exception as e:
            print(f"Failed to load or precalculate indicators for {pair_key}: {e}")

    if not pair_dfs:
        print("No valid pairs loaded. Exiting.")
        return 1

    results = {}

    if args.mode == "individual":
        for pair_key, df in pair_dfs.items():
            s1, s2 = pair_key.split("-")
            pair_results = {}
            for w in windows:
                window_bars = w * 96
                sim_res = tester.run_trading_simulation(s1, s2, df, window_bars=window_bars)
                pair_results[f"window_{w}d"] = {
                    "trades": sim_res["trades"],
                    "net_profit_pct": sim_res["net_profit_pct"],
                    "win_rate": sim_res["win_rate"],
                    "avg_pnl_pct": sim_res["avg_pnl_pct"]
                }
            results[pair_key] = pair_results
    else:
        # Portfolio mode
        portfolio_results = {}
        for w in windows:
            window_bars = w * 96
            sim_res = tester.run_portfolio_simulation(pair_dfs, window_bars=window_bars)
            portfolio_results[f"window_{w}d"] = {
                "trades": sim_res.get("trades", 0),
                "net_profit_pct": sim_res.get("net_profit_pct", 0.0),
                "win_rate": sim_res.get("win_rate", 0.0),
                "avg_pnl_pct": sim_res.get("avg_pnl_pct", 0.0),
                "max_drawdown_pct": sim_res.get("max_drawdown_pct", 0.0),
                "sharpe_ratio": sim_res.get("sharpe_ratio", 0.0),
            }
            print(f"Window {w}d backtested: trades={sim_res.get('trades')}, return={sim_res.get('net_profit_pct'):+.2f}%, sharpe={sim_res.get('sharpe_ratio')}, max_dd={sim_res.get('max_drawdown_pct')}%")
        results["portfolio"] = portfolio_results

    # Write out report
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved validation report to {args.out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
