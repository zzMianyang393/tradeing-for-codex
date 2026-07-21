"""Native Binance COIN-M OI-flush reversal research backtest.

This is a market-structure hypothesis test, not an OKX execution backtest.  It
uses only same-market daily price and OI data, enters on the next day's open,
and includes a configurable two-sided fee/slippage estimate.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DailyBar:
    day: str
    open: float
    high: float
    low: float
    close: float
    oi_value: float


@dataclass(frozen=True)
class NativeTrade:
    entry_day: str
    exit_day: str
    entry: float
    exit: float
    net_return_pct: float
    exit_reason: str


def load_native_bars(kline_path: Path, metrics_path: Path) -> list[DailyBar]:
    oi_by_day: dict[str, float] = {}
    with metrics_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                oi_by_day[row["archive_date"]] = float(row["sum_open_interest_value"])
            except (KeyError, TypeError, ValueError):
                continue
    bars: list[DailyBar] = []
    with kline_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                day = __import__("datetime").datetime.fromtimestamp(int(row["open_time"]) / 1000, tz=__import__("datetime").timezone.utc).date().isoformat()
                if day not in oi_by_day:
                    continue
                bars.append(DailyBar(day, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), oi_by_day[day]))
            except (KeyError, TypeError, ValueError, OSError):
                continue
    return sorted(bars, key=lambda item: item.day)


def _atr(bars: list[DailyBar], index: int, window: int = 14) -> float:
    if index < window:
        return 0.0
    ranges = []
    for current in range(index - window + 1, index + 1):
        previous_close = bars[current - 1].close if current else bars[current].close
        ranges.append(max(bars[current].high - bars[current].low, abs(bars[current].high - previous_close), abs(bars[current].low - previous_close)))
    return sum(ranges) / len(ranges)


def _oi_zscore(bars: list[DailyBar], index: int, window: int = 60) -> float | None:
    if index < window + 1 or bars[index - 1].oi_value <= 0:
        return None
    change = bars[index].oi_value / bars[index - 1].oi_value - 1.0
    history = [bars[item].oi_value / bars[item - 1].oi_value - 1.0 for item in range(index - window, index)]
    mean = sum(history) / len(history)
    variance = sum((value - mean) ** 2 for value in history) / len(history)
    deviation = math.sqrt(variance)
    return (change - mean) / deviation if deviation else None


def run_oi_flush_reversal(bars: list[DailyBar], fee: float = 0.0005, slippage: float = 0.0005) -> dict[str, Any]:
    """Fixed rule: OI change z <= -2, 3d price flush <= -5%, green reclaim day."""
    trades: list[NativeTrade] = []
    equity = 1.0
    peak = equity
    max_drawdown = 0.0
    position: dict[str, Any] | None = None
    for index in range(1, len(bars)):
        bar = bars[index]
        if position is not None:
            if bar.low <= position["stop"]:
                exit_price, reason = position["stop"] * (1.0 - slippage), "stop"
            elif bar.high >= position["take"]:
                exit_price, reason = position["take"] * (1.0 - slippage), "take_profit"
            elif index >= position["expiry"]:
                exit_price, reason = bar.close * (1.0 - slippage), "time_exit"
            else:
                exit_price = None
                reason = ""
            if exit_price is not None:
                # Entry and exit are both chargeable; price slippage is already
                # embedded in the two prices above.
                net_return = exit_price / position["entry"] - 1.0 - 2.0 * fee
                equity *= 1.0 + net_return
                trades.append(NativeTrade(position["entry_day"], bar.day, position["entry"], exit_price, net_return * 100.0, reason))
                position = None
        if position is None and index >= 64:
            signal_day = bars[index - 1]
            zscore = _oi_zscore(bars, index - 1)
            three_day_move = signal_day.close / bars[index - 4].close - 1.0
            atr = _atr(bars, index - 1)
            if zscore is not None and zscore <= -2.0 and three_day_move <= -0.05 and signal_day.close > signal_day.open and atr > 0:
                entry = bar.open * (1.0 + slippage)
                position = {"entry_day": bar.day, "entry": entry, "stop": entry - 2.0 * atr, "take": entry + 3.0 * atr, "expiry": index + 3}
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
    total_return = (equity - 1.0) * 100.0
    wins = sum(item.net_return_pct > 0 for item in trades)
    return {"trades": len(trades), "win_rate": wins / len(trades) if trades else 0.0, "return_pct": total_return, "max_drawdown_pct": max_drawdown * 100.0, "trades_detail": [asdict(item) for item in trades]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run native Binance COIN-M OI-flush research.")
    parser.add_argument("--data", type=Path, default=Path("data/external"))
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD_PERP", "ETHUSD_PERP"])
    parser.add_argument("--out", type=Path, default=Path("reports/native_oi_research.json"))
    args = parser.parse_args(argv)
    result = {"scope": "research_native_only_not_okx_execution", "symbols": {}}
    for symbol in args.symbols:
        bars = load_native_bars(args.data / f"{symbol}_binance_cm_1d.csv", args.data / f"{symbol}_binance_cm_metrics.csv")
        result["symbols"][symbol] = {"rows": len(bars), "base": run_oi_flush_reversal(bars), "stress": run_oi_flush_reversal(bars, fee=0.001, slippage=0.001)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
