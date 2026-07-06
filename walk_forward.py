from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from config import BacktestConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WindowResult:
    train_days: int = 0
    test_days: int = 0
    train_pnl: float = 0.0
    test_pnl: float = 0.0
    train_win_rate: float = 0.0
    test_win_rate: float = 0.0
    train_trades: int = 0
    test_trades: int = 0
    degradation: float = 0.0  # (train_pnl - test_pnl) / abs(train_pnl)


@dataclass
class WalkForwardReport:
    windows: list[WindowResult] | None = None
    avg_oos_pnl: float = 0.0
    avg_oos_win_rate: float = 0.0
    avg_degradation: float = 0.0
    overfitting_score: float = 0.0  # 0-1, higher = more overfitting
    passed: bool = False


# ---------------------------------------------------------------------------
# Walk-Forward testing
# ---------------------------------------------------------------------------

def run_walk_forward(
    market: dict[str, Any],
    config: BacktestConfig,
    train_days: int = 180,
    test_days: int = 30,
    step_days: int = 30,
    min_windows: int = 3,
) -> WalkForwardReport:
    """Run walk-forward optimization and testing.

    Splits data into rolling train/test windows:
    1. Train on [start, start+train_days]
    2. Test on [start+train_days, start+train_days+test_days]
    3. Step forward by step_days
    4. Repeat

    Returns aggregate OOS performance metrics.
    """
    from backtester import Backtester, _common_timeline

    report = WalkForwardReport(windows=[])

    # Get full timeline
    timeline = _common_timeline(market, min_count_fraction=0.50)
    if not timeline:
        logger.warning("No timeline data for walk-forward")
        return report

    # Calculate time range in ms
    total_ms = timeline[-1] - timeline[0]
    train_ms = train_days * 24 * 3600 * 1000
    test_ms = test_days * 24 * 3600 * 1000
    step_ms = step_days * 24 * 3600 * 1000

    # Generate windows
    windows: list[WindowResult] = []
    start_ms = timeline[0]

    while start_ms + train_ms + test_ms <= timeline[-1]:
        # Split timeline into train/test
        train_end = start_ms + train_ms
        test_end = train_end + test_ms

        # Filter market data for train period
        train_market = _filter_market(market, start_ms, train_end)
        test_market = _filter_market(market, train_end, test_end)

        if not train_market or not test_market:
            start_ms += step_ms
            continue

        # Run backtest on train
        train_result = _run_backtest(train_market, config, train_days)
        # Run backtest on test (out-of-sample)
        test_result = _run_backtest(test_market, config, test_days)

        if train_result and test_result:
            train_pnl = train_result.get("pnl", 0)
            test_pnl = test_result.get("pnl", 0)
            train_wr = train_result.get("win_rate", 0)
            test_wr = test_result.get("win_rate", 0)
            train_trades = train_result.get("trades", 0)
            test_trades = test_result.get("trades", 0)

            degradation = 0.0
            if abs(train_pnl) > 0.001:
                degradation = (train_pnl - test_pnl) / abs(train_pnl)

            windows.append(WindowResult(
                train_days=train_days,
                test_days=test_days,
                train_pnl=train_pnl,
                test_pnl=test_pnl,
                train_win_rate=train_wr,
                test_win_rate=test_wr,
                train_trades=train_trades,
                test_trades=test_trades,
                degradation=degradation,
            ))

        start_ms += step_ms

    report.windows = windows

    # Aggregate metrics
    if windows:
        report.avg_oos_pnl = sum(w.test_pnl for w in windows) / len(windows)
        report.avg_oos_win_rate = sum(w.test_win_rate for w in windows) / len(windows)
        report.avg_degradation = sum(w.degradation for w in windows) / len(windows)

        # Overfitting score: 0-1, higher = more overfitting
        # Based on: degradation consistency + OOS variance
        degradations = [w.degradation for w in windows]
        avg_deg = report.avg_degradation
        variance = sum((d - avg_deg) ** 2 for d in degradations) / len(degradations)
        report.overfitting_score = min(1.0, max(0.0, avg_deg * 0.5 + variance * 0.5))

        report.passed = (
            len(windows) >= min_windows
            and report.avg_oos_pnl > 0
            and report.overfitting_score < 0.6
        )

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_market(market: dict, start_ms: int, end_ms: int) -> dict:
    """Filter market data to a time range."""
    filtered = {}
    for symbol, bars in market.items():
        filtered_bars = [b for b in bars if start_ms <= b.ts < end_ms]
        if filtered_bars:
            filtered[symbol] = filtered_bars
    return filtered


def _run_backtest(market: dict, config: BacktestConfig, days: int) -> dict | None:
    """Run a backtest and return results."""
    try:
        from backtester import Backtester
        tester = Backtester(config)
        return tester.run(market, days=days)
    except Exception as e:
        logger.warning(f"Backtest failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------

def save_walk_forward_report(report: WalkForwardReport, path: Path) -> None:
    """Save walk-forward report to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(report)
    # Handle None windows
    if data.get("windows") is None:
        data["windows"] = []
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_walk_forward_report(path: Path) -> WalkForwardReport:
    """Load walk-forward report from JSON."""
    if not path.exists():
        return WalkForwardReport()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        windows = [WindowResult(**w) for w in data.get("windows", [])]
        return WalkForwardReport(
            windows=windows,
            avg_oos_pnl=data.get("avg_oos_pnl", 0),
            avg_oos_win_rate=data.get("avg_oos_win_rate", 0),
            avg_degradation=data.get("avg_degradation", 0),
            overfitting_score=data.get("overfitting_score", 0),
            passed=data.get("passed", False),
        )
    except Exception as e:
        logger.warning(f"Failed to load walk-forward report: {e}")
        return WalkForwardReport()
