"""Native Binance COIN-M taker-flow absorption research backtest.

This fixed daily hypothesis treats an extreme aggressive order-flow imbalance
that fails to move price in its own direction as absorption.  It is research
on the source market only, never a claim about OKX execution performance.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DailyFlowBar:
    day: str
    open: float
    high: float
    low: float
    close: float
    taker_ratio: float


@dataclass(frozen=True)
class FlowTrade:
    direction: int
    entry_day: str
    exit_day: str
    net_return_pct: float
    exit_reason: str


def load_flow_bars(kline_path: Path, metrics_path: Path) -> list[DailyFlowBar]:
    ratio_by_day: dict[str, float] = {}
    with metrics_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                ratio = float(row["sum_taker_long_short_vol_ratio"])
                if ratio > 0 and math.isfinite(ratio):
                    ratio_by_day[row["archive_date"]] = ratio
            except (KeyError, TypeError, ValueError):
                continue
    bars: list[DailyFlowBar] = []
    with kline_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                day = datetime.fromtimestamp(int(row["open_time"]) / 1000, tz=timezone.utc).date().isoformat()
                if day in ratio_by_day:
                    bars.append(DailyFlowBar(day, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), ratio_by_day[day]))
            except (KeyError, TypeError, ValueError, OSError):
                continue
    return sorted(bars, key=lambda item: item.day)


def _atr(bars: list[DailyFlowBar], index: int, window: int = 14) -> float:
    if index < window:
        return 0.0
    ranges = []
    for current in range(index - window + 1, index + 1):
        previous_close = bars[current - 1].close if current else bars[current].close
        ranges.append(max(bars[current].high - bars[current].low, abs(bars[current].high - previous_close), abs(bars[current].low - previous_close)))
    return sum(ranges) / len(ranges)


def _flow_zscore(bars: list[DailyFlowBar], index: int, window: int = 60) -> float | None:
    if index < window:
        return None
    values = [math.log(bars[item].taker_ratio) for item in range(index - window, index)]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    deviation = math.sqrt(variance)
    return (math.log(bars[index].taker_ratio) - mean) / deviation if deviation else None


def run_taker_absorption(bars: list[DailyFlowBar], fee: float = 0.0005, slippage: float = 0.0005) -> dict[str, Any]:
    """Fixed rule: 60d flow z >= 2/< = -2 with opposite daily close direction."""
    trades: list[FlowTrade] = []
    equity = peak = 1.0
    max_drawdown = 0.0
    position: dict[str, Any] | None = None
    for index in range(1, len(bars)):
        bar = bars[index]
        if position is not None:
            direction = position["direction"]
            if (direction == 1 and bar.low <= position["stop"]) or (direction == -1 and bar.high >= position["stop"]):
                exit_price, reason = position["stop"] * (1.0 - direction * slippage), "stop"
            elif (direction == 1 and bar.high >= position["take"]) or (direction == -1 and bar.low <= position["take"]):
                exit_price, reason = position["take"] * (1.0 - direction * slippage), "take_profit"
            elif index >= position["expiry"]:
                exit_price, reason = bar.close * (1.0 - direction * slippage), "time_exit"
            else:
                exit_price, reason = None, ""
            if exit_price is not None:
                gross = direction * (exit_price / position["entry"] - 1.0)
                # ``fee`` is per side; entry/exit slippage is already included
                # in the prices used to calculate ``gross``.
                net_return = gross - 2.0 * fee
                equity *= 1.0 + net_return
                trades.append(FlowTrade(direction, position["entry_day"], bar.day, net_return * 100.0, reason))
                position = None
        if position is None and index >= 61:
            signal_day = bars[index - 1]
            zscore = _flow_zscore(bars, index - 1)
            day_return = signal_day.close / signal_day.open - 1.0 if signal_day.open else 0.0
            atr = _atr(bars, index - 1)
            direction = 1 if zscore is not None and zscore <= -2.0 and day_return > 0 else -1 if zscore is not None and zscore >= 2.0 and day_return < 0 else 0
            if direction and atr > 0:
                entry = bar.open * (1.0 + direction * slippage)
                position = {
                    "direction": direction,
                    "entry_day": bar.day,
                    "entry": entry,
                    "stop": entry - direction * 2.0 * atr,
                    "take": entry + direction * 3.0 * atr,
                    "expiry": index + 3,
                }
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
    wins = sum(item.net_return_pct > 0 for item in trades)
    return {
        "trades": len(trades),
        "win_rate": wins / len(trades) if trades else 0.0,
        "return_pct": (equity - 1.0) * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "trades_detail": [asdict(item) for item in trades],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run native Binance COIN-M taker-flow absorption research.")
    parser.add_argument("--data", type=Path, default=Path("data/external"))
    parser.add_argument("--symbols", nargs="+", default=["BTCUSD_PERP", "ETHUSD_PERP"])
    parser.add_argument("--out", type=Path, default=Path("reports/native_taker_flow_research.json"))
    args = parser.parse_args(argv)
    result: dict[str, Any] = {"scope": "research_native_only_not_okx_execution", "symbols": {}}
    for symbol in args.symbols:
        bars = load_flow_bars(args.data / f"{symbol}_binance_cm_1d.csv", args.data / f"{symbol}_binance_cm_metrics.csv")
        result["symbols"][symbol] = {"rows": len(bars), "base": run_taker_absorption(bars), "stress": run_taker_absorption(bars, fee=0.001, slippage=0.001)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
