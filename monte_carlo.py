from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MonteCarloResult:
    simulation_id: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    final_equity: float = 0.0


@dataclass
class MonteCarloReport:
    n_simulations: int = 0
    original_pnl: float = 0.0
    original_win_rate: float = 0.0
    original_max_drawdown: float = 0.0
    mean_pnl: float = 0.0
    std_pnl: float = 0.0
    p5_pnl: float = 0.0  # 5th percentile (worst case)
    p25_pnl: float = 0.0  # 25th percentile
    p50_pnl: float = 0.0  # median
    p75_pnl: float = 0.0  # 75th percentile
    p95_pnl: float = 0.0  # 95th percentile (best case)
    mean_max_drawdown: float = 0.0
    p95_max_drawdown: float = 0.0  # 95th percentile drawdown
    mean_win_rate: float = 0.0
    mean_sharpe: float = 0.0
    positive_pct: float = 0.0  # % of simulations with positive PnL
    results: list[MonteCarloResult] | None = None
    passed: bool = False


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------

def run_monte_carlo(
    trades: list[dict],
    n_simulations: int = 1000,
    initial_equity: float = 10.0,
    seed: int | None = None,
) -> MonteCarloReport:
    """Run Monte Carlo simulation by shuffling trade order.

    Reshuffles the trade sequence many times and computes statistics
    on the distribution of outcomes. This tests whether the strategy's
    performance depends on specific trade ordering.

    Args:
        trades: List of trade dicts with 'pnl' key
        n_simulations: Number of Monte Carlo iterations
        initial_equity: Starting equity
        seed: Random seed for reproducibility
    """
    if not trades:
        return MonteCarloReport(n_simulations=0)

    # Extract PnL values
    pnls = [t.get("pnl", 0) for t in trades]
    wins = [t for t in trades if t.get("pnl", 0) > 0]

    # Original stats
    original_pnl = sum(pnls)
    original_wr = len(wins) / len(trades) if trades else 0
    original_dd = _max_drawdown(pnls, initial_equity)

    # Run simulations
    rng = random.Random(seed)
    results: list[MonteCarloResult] = []

    for i in range(n_simulations):
        # Shuffle trades
        shuffled_pnls = pnls[:]
        rng.shuffle(shuffled_pnls)

        # Calculate metrics
        total_pnl = sum(shuffled_pnls)
        dd = _max_drawdown(shuffled_pnls, initial_equity)
        sim_wr = sum(1 for p in shuffled_pnls if p > 0) / len(shuffled_pnls) if shuffled_pnls else 0
        sharpe = _sharpe_ratio(shuffled_pnls)
        final_eq = initial_equity + total_pnl

        results.append(MonteCarloResult(
            simulation_id=i,
            total_pnl=total_pnl,
            max_drawdown=dd,
            win_rate=sim_wr,
            sharpe_ratio=sharpe,
            final_equity=final_eq,
        ))

    # Calculate statistics
    report = _compute_statistics(results, original_pnl, original_wr, original_dd, n_simulations)

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _max_drawdown(pnls: list[float], initial_equity: float) -> float:
    """Calculate maximum drawdown from PnL series."""
    equity = initial_equity
    peak = equity
    max_dd = 0.0

    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return max_dd


def _sharpe_ratio(pnls: list[float], risk_free_rate: float = 0.0) -> float:
    """Calculate Sharpe ratio from PnL series."""
    if not pnls or len(pnls) < 2:
        return 0.0

    mean_return = sum(pnls) / len(pnls)
    variance = sum((p - mean_return) ** 2 for p in pnls) / (len(pnls) - 1)
    std_dev = math.sqrt(variance)

    if std_dev < 1e-10:  # Use small threshold for floating point comparison
        return 0.0

    return (mean_return - risk_free_rate) / std_dev


def _percentile(values: list[float], p: float) -> float:
    """Calculate percentile using linear interpolation."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    k = (n - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[int(f)] * (c - k) + sorted_vals[int(c)] * (k - f)


def _compute_statistics(
    results: list[MonteCarloResult],
    original_pnl: float,
    original_wr: float,
    original_dd: float,
    n_simulations: int,
) -> MonteCarloReport:
    """Compute aggregate statistics from simulation results."""
    pnls = [r.total_pnl for r in results]
    dds = [r.max_drawdown for r in results]
    wrs = [r.win_rate for r in results]
    sharpes = [r.sharpe_ratio for r in results]

    mean_pnl = sum(pnls) / len(pnls)
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
    std_pnl = math.sqrt(variance)

    positive_count = sum(1 for p in pnls if p > 0)

    return MonteCarloReport(
        n_simulations=n_simulations,
        original_pnl=original_pnl,
        original_win_rate=original_wr,
        original_max_drawdown=original_dd,
        mean_pnl=mean_pnl,
        std_pnl=std_pnl,
        p5_pnl=_percentile(pnls, 0.05),
        p25_pnl=_percentile(pnls, 0.25),
        p50_pnl=_percentile(pnls, 0.50),
        p75_pnl=_percentile(pnls, 0.75),
        p95_pnl=_percentile(pnls, 0.95),
        mean_max_drawdown=sum(dds) / len(dds),
        p95_max_drawdown=_percentile(dds, 0.95),
        mean_win_rate=sum(wrs) / len(wrs),
        mean_sharpe=sum(sharpes) / len(sharpes),
        positive_pct=positive_count / len(results),
        results=results,
        passed=(
            positive_count / len(results) > 0.5  # >50% positive
            and _percentile(pnls, 0.05) > -10.0 * 0.5  # 5th pct not catastrophic
        ),
    )


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------

def save_monte_carlo_report(report: MonteCarloReport, path: Path) -> None:
    """Save Monte Carlo report to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(report)
    # Limit results stored (too many for large simulations)
    if data.get("results") and len(data["results"]) > 100:
        data["results"] = data["results"][:100]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_monte_carlo_report(path: Path) -> MonteCarloReport:
    """Load Monte Carlo report from JSON."""
    if not path.exists():
        return MonteCarloReport()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        results = [MonteCarloResult(**r) for r in data.get("results", [])]
        return MonteCarloReport(
            n_simulations=data.get("n_simulations", 0),
            original_pnl=data.get("original_pnl", 0),
            original_win_rate=data.get("original_win_rate", 0),
            original_max_drawdown=data.get("original_max_drawdown", 0),
            mean_pnl=data.get("mean_pnl", 0),
            std_pnl=data.get("std_pnl", 0),
            p5_pnl=data.get("p5_pnl", 0),
            p25_pnl=data.get("p25_pnl", 0),
            p50_pnl=data.get("p50_pnl", 0),
            p75_pnl=data.get("p75_pnl", 0),
            p95_pnl=data.get("p95_pnl", 0),
            mean_max_drawdown=data.get("mean_max_drawdown", 0),
            p95_max_drawdown=data.get("p95_max_drawdown", 0),
            mean_win_rate=data.get("mean_win_rate", 0),
            mean_sharpe=data.get("mean_sharpe", 0),
            positive_pct=data.get("positive_pct", 0),
            results=results,
            passed=data.get("passed", False),
        )
    except Exception as e:
        logger.warning(f"Failed to load Monte Carlo report: {e}")
        return MonteCarloReport()
