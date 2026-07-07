from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from backtester import run_report
from config import BacktestConfig
from market import load_market
from monte_carlo import run_monte_carlo
from param_sensitivity import run_sensitivity
from validation import audit_report
from walk_forward import run_walk_forward


def check_single_trade_contribution(
    trades: list[dict[str, Any]],
    top_n: int = 2,
    max_share: float = 0.70,
) -> dict[str, Any]:
    positive_pnls = sorted(
        [float(trade.get("pnl") or 0.0) for trade in trades if float(trade.get("pnl") or 0.0) > 0],
        reverse=True,
    )
    total_positive = sum(positive_pnls)
    if len(positive_pnls) <= top_n or total_positive <= 0:
        return {
            "passed": True,
            "reason": "insufficient_positive_trades",
            "top_n": top_n,
            "top_positive_share": 0.0,
            "positive_trades": len(positive_pnls),
            "max_share": max_share,
        }
    top_share = sum(positive_pnls[:top_n]) / total_positive
    return {
        "passed": top_share <= max_share,
        "reason": "ok" if top_share <= max_share else "top_trades_dominate_positive_pnl",
        "top_n": top_n,
        "top_positive_share": round(top_share, 4),
        "positive_trades": len(positive_pnls),
        "max_share": max_share,
    }


def run_drawdown_stress(
    trades: list[dict[str, Any]],
    initial_equity: float = 10.0,
    loss_multiplier: float = 1.5,
    max_drawdown_limit: float = 0.45,
) -> dict[str, Any]:
    stressed_pnls = []
    for trade in trades:
        pnl = float(trade.get("pnl") or 0.0)
        stressed_pnls.append(pnl * loss_multiplier if pnl < 0 else pnl)
    max_drawdown = _max_drawdown(stressed_pnls, initial_equity)
    return {
        "passed": max_drawdown <= max_drawdown_limit,
        "max_drawdown": round(max_drawdown, 4),
        "max_drawdown_limit": max_drawdown_limit,
        "loss_multiplier": loss_multiplier,
        "trades": len(trades),
    }


def run_full_validation(
    market: dict[str, Any],
    config: BacktestConfig,
    latest_report: dict[str, Any],
    required_windows: tuple[int, ...] = (365, 180, 90, 60, 30, 14, 7),
    monte_carlo_simulations: int = 1000,
    initial_equity: float | None = None,
) -> dict[str, Any]:
    initial_equity = config.start_equity if initial_equity is None else initial_equity
    trades = list(latest_report.get("trades_detail") or [])
    latest_audit = audit_report(
        latest_report,
        required_windows=required_windows,
        min_win_rate=0.60,
    )
    walk_forward_report = run_walk_forward(market, config)
    sensitivity_report = run_sensitivity(market, config)
    monte_carlo_report = run_monte_carlo(
        trades,
        n_simulations=monte_carlo_simulations,
        initial_equity=initial_equity,
        seed=7,
    )
    contribution = check_single_trade_contribution(trades)
    drawdown_stress = run_drawdown_stress(trades, initial_equity=initial_equity)
    sections_passed = [
        latest_audit.get("complete", False),
        bool(getattr(walk_forward_report, "passed", False)),
        bool(getattr(sensitivity_report, "passed", False)),
        bool(getattr(monte_carlo_report, "passed", False)),
        contribution["passed"],
        drawdown_stress["passed"],
    ]
    return {
        "complete": all(sections_passed),
        "latest": latest_audit,
        "walk_forward": asdict(walk_forward_report),
        "sensitivity": asdict(sensitivity_report),
        "monte_carlo": _limited_monte_carlo_dict(monte_carlo_report),
        "single_trade_contribution": contribution,
        "drawdown_stress": drawdown_stress,
    }


def load_config(path: Path | None) -> BacktestConfig:
    config = BacktestConfig()
    if path is None:
        return config
    data = json.loads(path.read_text(encoding="utf-8"))
    overrides = {key: value for key, value in data.items() if hasattr(config, key)}
    return replace(config, **overrides)


def save_full_validation_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def _max_drawdown(pnls: list[float], initial_equity: float) -> float:
    equity = initial_equity
    peak = equity
    max_drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def _limited_monte_carlo_dict(report: Any) -> dict[str, Any]:
    data = asdict(report)
    if data.get("results") and len(data["results"]) > 100:
        data["results"] = data["results"][:100]
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the full anti-overfit validation pipeline.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports") / "full_validation.json")
    parser.add_argument("--required-windows", nargs="+", type=int, default=[365, 180, 90, 60, 30, 14, 7])
    parser.add_argument("--monte-carlo-sims", type=int, default=1000)
    parser.add_argument("--initial-equity", type=float)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    market = load_market(args.data, config.timeframe_minutes)
    latest_path = args.out.with_name(args.out.stem + "_latest.json")
    latest_report = run_report(args.data, latest_path, config)
    report = run_full_validation(
        market=market,
        config=config,
        latest_report=latest_report,
        required_windows=tuple(args.required_windows),
        monte_carlo_simulations=args.monte_carlo_sims,
        initial_equity=args.initial_equity,
    )
    save_full_validation_report(report, args.out)
    print(f"Wrote full validation report to {args.out}", flush=True)
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
