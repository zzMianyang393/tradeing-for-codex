from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from goal_search import market_feature_flags_for_configs
from market import load_market
from staged_goal import load_top_configs_from_report_payload
from strategy_adaptation_audit import translate_reason


def _balanced_allows(row: dict) -> bool:
    if row.get("adaptability_cn") == "强":
        return True
    return (
        row.get("reason", "").startswith("transition_breakout_")
        and float(row.get("pnl", 0.0)) > 0
        and float(row.get("median_month_pnl", 0.0)) >= -5.0
        and float(row.get("profit_month_ratio", 0.0)) >= 0.5
        and float(row.get("win_rate", 0.0)) >= 0.55
        and int(row.get("trades", 0)) >= 30
    )


def build_router_profile(adaptation_report: dict, mode: str = "conservative") -> dict:
    if mode not in {"conservative", "balanced", "cautious"}:
        raise ValueError("mode must be conservative, balanced, or cautious")
    rows = list(adaptation_report.get("strategies", []))
    allowed = sorted(
        row["reason"]
        for row in rows
        if row.get("adaptability_cn") == "强" or (mode in {"balanced", "cautious"} and _balanced_allows(row))
    )
    blocked = sorted(row["reason"] for row in rows if row["reason"] not in set(allowed))
    reason_risk_multipliers = {
        row["reason"]: 0.35
        for row in rows
        if mode == "cautious" and row["reason"] in set(allowed) and row.get("adaptability_cn") != "强"
    }
    return {
        "mode": mode,
        "allowed_reasons": tuple(allowed),
        "blocked_reasons": tuple(blocked),
        "reason_risk_multipliers": reason_risk_multipliers,
        "allowed_reasons_cn": [translate_reason(reason) for reason in allowed],
        "blocked_reasons_cn": [translate_reason(reason) for reason in blocked],
    }


def apply_router_profile(config: BacktestConfig, profile: dict) -> BacktestConfig:
    reason_risk_multipliers = dict(config.reason_risk_multipliers)
    reason_risk_multipliers.update(profile.get("reason_risk_multipliers", {}))
    return replace(
        config,
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=tuple(profile.get("allowed_reasons", ())),
        router_blocked_reasons=tuple(profile.get("blocked_reasons", ())),
        reason_risk_multipliers=reason_risk_multipliers,
    )


def _load_ranked_configs(paths: tuple[Path, ...], limit: int) -> list[dict]:
    configs: list[dict] = []
    seen: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in load_top_configs_from_report_payload(payload, limit):
            key = json.dumps(item["config"].__dict__, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            configs.append({"rank": f"{path.stem}#{item['rank']}", "config": item["config"]})
    return configs


def filter_ranked_configs(ranked_configs: list[dict], rank_filter: tuple[str, ...]) -> list[dict]:
    if not rank_filter:
        return ranked_configs
    wanted = set(rank_filter)
    return [item for item in ranked_configs if item["rank"] in wanted]


def build_transition_long_variants(ranked_configs: list[dict]) -> list[dict]:
    variants = list(ranked_configs)
    min_scores = (2.25, 2.45, 2.7)
    move_filters = (-1.0, -0.05, 0.02)
    risk_multipliers = (0.6, 0.85)
    for item in ranked_configs:
        base = item["config"]
        variant_index = 1
        for min_score in min_scores:
            for move_filter in move_filters:
                for risk_multiplier in risk_multipliers:
                    variants.append(
                        {
                            "rank": f"{item['rank']}.transition{variant_index}",
                            "source_rank": item["rank"],
                            "config": replace(
                                base,
                                min_score=min_score,
                                transition_long_enabled=True,
                                transition_short_enabled=False,
                                transition_long_min_move_21d=move_filter,
                                risk_per_trade=max(0.01, base.risk_per_trade * risk_multiplier),
                            ),
                        }
                    )
                    variant_index += 1
    return variants


def compact_result(result: dict) -> dict:
    return {
        "end_equity": result.get("end_equity"),
        "pnl": result.get("pnl"),
        "return_pct": result.get("return_pct"),
        "max_drawdown_pct": result.get("max_drawdown_pct"),
        "trades": result.get("trades"),
        "win_rate": result.get("win_rate"),
        "by_reason": result.get("by_reason", {}),
        "by_regime": result.get("by_regime", {}),
    }


def run_router_experiment(
    market: dict,
    ranked_configs: list[dict],
    profile: dict,
    days: int,
    start_equity: float,
) -> dict:
    results: list[dict] = []
    for item in ranked_configs:
        config = apply_router_profile(replace(item["config"], start_equity=start_equity), profile)
        result = Backtester(config).run(market, days=days)
        results.append({"rank": item["rank"], "result": compact_result(result)})
    results.sort(
        key=lambda item: (
            float(item["result"].get("pnl", 0.0)),
            -float(item["result"].get("max_drawdown_pct", 999.0)),
            int(item["result"].get("trades", 0)),
        ),
        reverse=True,
    )
    return {
        "days": days,
        "start_equity": start_equity,
        "router_profile": profile,
        "best": results[0] if results else None,
        "top": results[: min(20, len(results))],
        "searched": len(results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a continuous backtest with dynamic strategy router profile.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--adaptation-report", type=Path, default=Path("reports/strategy_adaptation_audit_prefer_qualified.json"))
    parser.add_argument("--reports", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--rank-filter", default="")
    parser.add_argument("--transition-variants", action="store_true")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--mode", choices=("conservative", "balanced", "cautious"), default="conservative")
    parser.add_argument("--start-equity", type=float, default=10.0)
    parser.add_argument("--out", type=Path, default=Path("reports/dynamic_router_experiment.json"))
    args = parser.parse_args()

    adaptation = json.loads(args.adaptation_report.read_text(encoding="utf-8"))
    profile = build_router_profile(adaptation, mode=args.mode)
    report_paths = tuple(Path(part.strip()) for part in args.reports.split(",") if part.strip())
    ranked = _load_ranked_configs(report_paths, args.limit)
    rank_filter = tuple(part.strip() for part in args.rank_filter.split(",") if part.strip())
    ranked = filter_ranked_configs(ranked, rank_filter)
    if args.transition_variants:
        ranked = build_transition_long_variants(ranked)
    routed_configs = [apply_router_profile(item["config"], profile) for item in ranked]
    market = load_market(
        args.data,
        BacktestConfig().timeframe_minutes,
        **market_feature_flags_for_configs(routed_configs),
    )
    report = run_router_experiment(
        market=market,
        ranked_configs=ranked,
        profile=profile,
        days=args.days,
        start_equity=args.start_equity,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    print(f"允许策略={','.join(profile['allowed_reasons_cn']) or '无'}")
    print(f"阻断策略={','.join(profile['blocked_reasons_cn']) or '无'}")
    best = report["best"]
    if best:
        result = best["result"]
        print(
            f"最佳配置={best['rank']} equity={result['end_equity']:.4f} pnl={result['pnl']:.4f} "
            f"return={result['return_pct']:.2f}% dd={result['max_drawdown_pct']:.2f}% "
            f"win={result['win_rate'] * 100:.2f}% trades={result['trades']}"
        )


if __name__ == "__main__":
    main()
