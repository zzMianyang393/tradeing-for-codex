# Tradering

`tradering` is a self-contained crypto perpetual backtesting and signal research program.

It uses local OKX 1m CSV data when available, resamples it to 15m bars, then runs a multi-symbol,
multi-regime strategy from a configurable starting balance.

## What it does

- Selects tradable symbols from the local data folder by liquidity, volatility, trend quality, and spread proxy.
- Handles uptrend, downtrend, and range regimes with different entry/exit logic.
- Sizes every trade from account equity, ATR stop distance, leverage caps, and portfolio exposure limits.
- Includes fees, slippage, stop loss, take profit, time stop, and trailing exit.
- Produces validation reports for the configured target windows.
- Marks unavailable windows when the selected symbol pool does not have enough overlapping data.
- Can download more OKX history with the included downloader.

This is research software, not a profit guarantee. It is intentionally built to report weak periods instead of hiding them.

## Quick start

```bash
cd E:\ai-trade\tradering
python run.py --report reports\quantify_latest.json
```

The default data path is `data`, which is included in this repository.
To run another local dataset, pass `--data <path>`.

## Download more data

```bash
cd E:\ai-trade\tradering
python okx_downloader.py --symbols BTC-USDT-SWAP ETH-USDT-SWAP SOL-USDT-SWAP --days 365 --bar 15m --out data
```

The downloader writes files in the same format as the existing local CSVs.

## Outputs

- `reports/latest.json`: machine-readable full report.
- Console summary: period PnL, win rate, drawdown, trade count, and symbol breakdown.

## Notes

- The included `data` folder contains the downloaded local research dataset used by the latest reports.
- The default profile is now an aggressive 10 USDT dynamic-universe short-window target profile.
- Allowed symbols: all loaded symbols; the program dynamically selects the top symbols each window.
- Enabled regimes: `uptrend`, `range`.
- Target gates: 30 day return >= 50%, 7 day return >= 20%, win rate >= 68%.

Latest default validation:

```text
30d  equity=23.2603  pnl=13.2603  return=132.603%  win=68.09%
7d   equity=13.6537  pnl=3.6537   return=36.537%   win=80.00%
```

Robustness note: this profile is an aggressive short-window mode. The included
`robustness_matrix.py` shows it does not generalize cleanly to 14/60 day gates,
major-only pools, or higher timeframes. Treat it as a tactical module, not a
validated all-weather strategy.
