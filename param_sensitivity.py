from __future__ import annotations

import copy
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
class ParamResult:
    param_name: str = ""
    base_value: float = 0.0
    perturbed_value: float = 0.0
    perturbation_pct: float = 0.0
    base_pnl: float = 0.0
    perturbed_pnl: float = 0.0
    pnl_change_pct: float = 0.0
    base_win_rate: float = 0.0
    perturbed_win_rate: float = 0.0


@dataclass
class SensitivityReport:
    params_tested: int = 0
    unstable_params: list[str] | None = None
    results: list[ParamResult] | None = None
    overall_stability: float = 0.0  # 0-1, higher = more stable
    passed: bool = False


# ---------------------------------------------------------------------------
# Default sensitive parameters to test
# ---------------------------------------------------------------------------

DEFAULT_SENSITIVE_PARAMS = [
    "risk_per_trade",
    "stop_atr",
    "take_profit_atr",
    "trailing_atr",
    "max_hold_bars",
    "cooldown_bars",
    "min_score",
    "max_margin_fraction",
    "max_total_margin_fraction",
]


# ---------------------------------------------------------------------------
# Parameter sensitivity testing
# ---------------------------------------------------------------------------

def run_sensitivity(
    market: dict[str, Any],
    config: BacktestConfig,
    param_ranges: dict[str, list[float]] | None = None,
    perturbations: list[float] | None = None,
    days: int = 90,
) -> SensitivityReport:
    """Test parameter sensitivity by perturbing key parameters.

    For each parameter, applies ±10% and ±20% perturbations and measures
    the impact on PnL and win rate. Large changes indicate instability.

    Args:
        market: Market data dict
        config: Base configuration
        param_ranges: Custom perturbation ranges per param. If None, uses
                      perturbations list with default params.
        perturbations: List of perturbation percentages (default: [-0.2, -0.1, 0.1, 0.2])
        days: Backtest window in days
    """
    if perturbations is None:
        perturbations = [-0.2, -0.1, 0.1, 0.2]

    # Run baseline
    base_result = _run_backtest(market, config, days)
    if not base_result:
        return SensitivityReport(passed=False)

    base_pnl = base_result.get("pnl", 0)
    base_wr = base_result.get("win_rate", 0)

    results: list[ParamResult] = []

    # Test each parameter
    params_to_test = list(param_ranges.keys()) if param_ranges else DEFAULT_SENSITIVE_PARAMS

    for param_name in params_to_test:
        base_value = getattr(config, param_name, None)
        if base_value is None or not isinstance(base_value, (int, float)):
            continue

        # Get perturbation values for this param
        if param_ranges and param_name in param_ranges:
            pcts = param_ranges[param_name]
        else:
            pcts = perturbations

        for pct in pcts:
            perturbed_value = base_value * (1 + pct)

            # Create perturbed config
            perturbed_config = _perturb_config(config, param_name, perturbed_value)

            # Run backtest with perturbed config
            perturbed_result = _run_backtest(market, perturbed_config, days)
            if not perturbed_result:
                continue

            perturbed_pnl = perturbed_result.get("pnl", 0)
            perturbed_wr = perturbed_result.get("win_rate", 0)

            pnl_change = 0.0
            if abs(base_pnl) > 0.001:
                pnl_change = (perturbed_pnl - base_pnl) / abs(base_pnl)

            results.append(ParamResult(
                param_name=param_name,
                base_value=base_value,
                perturbed_value=perturbed_value,
                perturbation_pct=pct,
                base_pnl=base_pnl,
                perturbed_pnl=perturbed_pnl,
                pnl_change_pct=pnl_change,
                base_win_rate=base_wr,
                perturbed_win_rate=perturbed_wr,
            ))

    # Analyze results
    report = SensitivityReport(
        params_tested=len(params_to_test),
        results=results,
    )

    # Find unstable params (large PnL swings)
    unstable = []
    param_impacts: dict[str, list[float]] = {}
    for r in results:
        if r.param_name not in param_impacts:
            param_impacts[r.param_name] = []
        param_impacts[r.param_name].append(abs(r.pnl_change_pct))

    for param_name, impacts in param_impacts.items():
        avg_impact = sum(impacts) / len(impacts) if impacts else 0
        if avg_impact > 0.3:  # >30% average change = unstable
            unstable.append(param_name)

    report.unstable_params = unstable

    # Overall stability score (0-1)
    all_impacts = [abs(r.pnl_change_pct) for r in results]
    avg_impact = sum(all_impacts) / len(all_impacts) if all_impacts else 0
    report.overall_stability = max(0.0, 1.0 - avg_impact)

    report.passed = len(unstable) == 0 and report.overall_stability > 0.5

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _perturb_config(config: BacktestConfig, param_name: str, value: Any) -> BacktestConfig:
    """Create a copy of config with one parameter changed."""
    from dataclasses import replace
    return replace(config, **{param_name: value})


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

def save_sensitivity_report(report: SensitivityReport, path: Path) -> None:
    """Save sensitivity report to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(report)
    if data.get("results") is None:
        data["results"] = []
    if data.get("unstable_params") is None:
        data["unstable_params"] = []
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_sensitivity_report(path: Path) -> SensitivityReport:
    """Load sensitivity report from JSON."""
    if not path.exists():
        return SensitivityReport()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        results = [ParamResult(**r) for r in data.get("results", [])]
        return SensitivityReport(
            params_tested=data.get("params_tested", 0),
            unstable_params=data.get("unstable_params", []),
            results=results,
            overall_stability=data.get("overall_stability", 0),
            passed=data.get("passed", False),
        )
    except Exception as e:
        logger.warning(f"Failed to load sensitivity report: {e}")
        return SensitivityReport()
