from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from config import BacktestConfig
from market import FeatureBar, load_market


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * q)))
    return ordered[idx]


def feature_row(trade: dict, bars: list[FeatureBar], time_index: dict[str, int]) -> dict[str, float]:
    idx = time_index[trade["entry_time"]]
    bar = bars[idx]
    prev = bars[idx - 1]
    lookback = bars[max(0, idx - 96) : idx + 1]
    move_1d = bar.close / lookback[0].close - 1.0 if lookback and lookback[0].close else 0.0
    vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma else 1.0
    candle_body = abs(bar.close - bar.open) / bar.close if bar.close else 0.0
    candle_range = (bar.high - bar.low) / bar.close if bar.close else 0.0
    band_width = (bar.bb_upper - bar.bb_lower) / bar.close if bar.close else 0.0
    ema_gap = (bar.ema20 - bar.ema50) / bar.close if bar.close else 0.0
    prev_body = abs(prev.close - prev.open) / prev.close if prev.close else 0.0
    return {
        "pnl": trade["pnl"],
        "win": 1.0 if trade["win"] else 0.0,
        "rsi": bar.rsi,
        "atr_pct": bar.atr_pct,
        "vol_ratio": vol_ratio,
        "candle_body": candle_body,
        "candle_range": candle_range,
        "prev_body": prev_body,
        "band_width": band_width,
        "trend_strength": bar.trend_strength,
        "ema_gap": ema_gap,
        "move_1d": move_1d,
        "close_vs_ema200": bar.close / bar.ema200 - 1.0 if bar.ema200 else 0.0,
    }


def print_group(name: str, rows: list[dict[str, float]]) -> None:
    print(f"\n{name} count={len(rows)} pnl={sum(row['pnl'] for row in rows):.4f}")
    for key in (
        "rsi",
        "atr_pct",
        "vol_ratio",
        "candle_body",
        "candle_range",
        "prev_body",
        "band_width",
        "trend_strength",
        "ema_gap",
        "move_1d",
        "close_vs_ema200",
    ):
        values = [row[key] for row in rows]
        print(f"  {key:16s} p25={pct(values, 0.25): .5f} p50={pct(values, 0.50): .5f} p75={pct(values, 0.75): .5f}")


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    cfg = BacktestConfig()
    market = load_market(Path("../Quantify/data"), cfg.timeframe_minutes)
    for days in ("60", "90"):
        rows_by_key: dict[tuple[str, str], list[dict[str, float]]] = defaultdict(list)
        for trade in report["windows"][days]["trades_detail"]:
            if not trade["reason"].startswith("range_revert_"):
                continue
            bars = market[trade["symbol"]]
            time_index = {bar.time: idx for idx, bar in enumerate(bars)}
            if trade["entry_time"] not in time_index:
                continue
            row = feature_row(trade, bars, time_index)
            rows_by_key[(trade["reason"], "win" if trade["win"] else "loss")].append(row)
        print(f"\n==== {days}d ====")
        for key, rows in sorted(rows_by_key.items()):
            print_group(" ".join(key), rows)


if __name__ == "__main__":
    main()
