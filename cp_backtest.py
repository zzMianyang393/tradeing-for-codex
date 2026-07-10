"""Run an honest candidate-pool backtest without an external model.

The CP model is trained only from the historical portion available inside the
backtest.  External models are intentionally disabled unless the caller uses
the lower-level BacktestConfig API explicitly and marks them as out-of-sample.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import discover_symbols, load_market


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an unbiased candidate-pool backtest.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--symbols", type=int, default=0, help="Limit symbols; 0 means all")
    parser.add_argument(
        "--retrain-interval-bars",
        type=int,
        default=96 * 7,
        help="CP ML retraining interval; use a large value for a performance baseline",
    )
    parser.add_argument("--report", type=Path, default=Path("reports/cp_unbiased_365d.json"))
    parser.add_argument("--candidate-cache", type=Path, default=None)
    parser.add_argument("--disable-risk", action="store_true", help="Diagnostic only: disable RiskManager")
    parser.add_argument("--disable-ml", action="store_true", help="Disable CP ML filter")
    parser.add_argument("--disable-rules", action="store_true", help="Disable CP rule filter")
    parser.add_argument("--direction", choices=("both", "long", "short"), default="both")
    parser.add_argument("--patterns", default="", help="Comma-separated CP patterns to enable")
    parser.add_argument(
        "--regimes",
        default="",
        help="Comma-separated market regimes to enable (uptrend,downtrend,transition,range)",
    )
    parser.add_argument(
        "--dynamic-regimes",
        action="store_true",
        help="Select regimes from prior labeled CP samples at each retrain",
    )
    parser.add_argument(
        "--dynamic-regime-risk",
        action="store_true",
        help="Scale CP risk by prior forward-PnL rate while keeping all regimes enabled",
    )
    parser.add_argument(
        "--quality-ranking",
        action="store_true",
        help="Rank candidates using prior pattern/regime/direction forward-PnL quality",
    )
    parser.add_argument(
        "--symbol-list",
        default="",
        help="Comma-separated symbols to load; overrides --symbols",
    )
    parser.add_argument("--cp-risk", type=float, default=0.10, help="Candidate-pool risk per trade")
    parser.add_argument("--cp-ml-estimators", type=int, default=32)
    parser.add_argument("--cp-stop-atr", type=float, default=2.0)
    parser.add_argument("--cp-take-profit-atr", type=float, default=1.2)
    parser.add_argument("--cp-trailing-atr", type=float, default=1.8)
    args = parser.parse_args()

    selected_symbols = None
    if args.symbol_list.strip():
        selected_symbols = {
            item.strip().upper() for item in args.symbol_list.split(",") if item.strip()
        }
    elif args.symbols > 0:
        selected_symbols = set(discover_symbols(args.data)[:args.symbols])
    print(f"Loading 15m market data from {args.data}...", flush=True)
    market = load_market(args.data, 15, symbols=selected_symbols)
    print(f"Loaded {len(market)} symbols; starting {args.days}d backtest...", flush=True)
    enabled_patterns = tuple(
        item.strip() for item in args.patterns.split(",") if item.strip()
    ) or BacktestConfig().cp_enabled_patterns
    enabled_regimes = tuple(
        item.strip() for item in args.regimes.split(",") if item.strip()
    ) or BacktestConfig().cp_enabled_regimes
    config = BacktestConfig(
        enable_candidate_pool=True,
        enable_target_window_profiles=False,
        cp_ml_model_path="",
        cp_allow_pretrained_model=False,
        cp_retrain_interval_bars=args.retrain_interval_bars,
        cp_candidate_cache_path=str(args.candidate_cache) if args.candidate_cache else "",
        rm_enabled=not args.disable_risk,
        cp_use_ml=not args.disable_ml,
        cp_use_rules=not args.disable_rules,
        cp_enabled_directions=(1,) if args.direction == "long" else (-1,) if args.direction == "short" else (1, -1),
        cp_enabled_regimes=enabled_regimes,
        cp_dynamic_regime_routing=args.dynamic_regimes,
        cp_dynamic_regime_risk_scaling=args.dynamic_regime_risk,
        cp_quality_ranking=args.quality_ranking,
        cp_enabled_patterns=enabled_patterns,
        cp_risk_per_trade=args.cp_risk,
        cp_ml_n_estimators=args.cp_ml_estimators,
        cp_stop_atr=args.cp_stop_atr,
        cp_take_profit_atr=args.cp_take_profit_atr,
        cp_trailing_atr=args.cp_trailing_atr,
    )
    report = Backtester(config).run(market, days=args.days)
    report["validation"] = {
        "kind": "candidate_pool_walk_forward",
        "external_model_loaded": False,
        "label_cutoff_enabled": True,
        "days": args.days,
        "retrain_interval_bars": args.retrain_interval_bars,
        "candidate_cache": str(args.candidate_cache) if args.candidate_cache else "",
        "risk_manager_enabled": not args.disable_risk,
        "cp_use_ml": not args.disable_ml,
        "cp_use_rules": not args.disable_rules,
        "direction": args.direction,
        "regimes": enabled_regimes,
        "dynamic_regimes": args.dynamic_regimes,
        "dynamic_regime_risk": args.dynamic_regime_risk,
        "quality_ranking": args.quality_ranking,
        "patterns": enabled_patterns,
        "cp_risk_per_trade": args.cp_risk,
        "cp_ml_estimators": args.cp_ml_estimators,
        "cp_exit": {
            "stop_atr": args.cp_stop_atr,
            "take_profit_atr": args.cp_take_profit_atr,
            "trailing_atr": args.cp_trailing_atr,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"{args.days}d CP: equity={report.get('end_equity', 0):.4f} "
        f"return={report.get('return_pct', 0):.3f}% "
        f"trades={report.get('trades', 0)} "
        f"dd={report.get('max_drawdown_pct', 0):.3f}%"
    )
    print(f"Report: {args.report}")


if __name__ == "__main__":
    main()
