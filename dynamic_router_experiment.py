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


_REGIME_CN = {
    "uptrend": "上涨趋势",
    "downtrend": "下跌趋势",
    "range": "震荡区间",
    "transition": "趋势转换",
}


def _default_allowed_regimes_for_reason(reason: str) -> tuple[str, ...]:
    if reason.endswith("_long") and reason.startswith("trend_"):
        return ("uptrend",)
    if reason.endswith("_short") and reason.startswith("trend_"):
        return ("downtrend",)
    if reason.startswith("transition_breakout_"):
        return ("transition",)
    if reason.startswith("range_revert_"):
        return ("range",)
    if reason.startswith("attack_breakout_long") or reason.startswith("micro_momentum_long"):
        return ("uptrend", "transition")
    if reason.startswith("attack_breakout_short") or reason.startswith("micro_momentum_short"):
        return ("downtrend", "transition")
    if reason.startswith("attack_exhaustion_"):
        return ("range",)
    if reason.startswith("continuation_"):
        return ("transition", "range")
    return ()


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
    if mode not in {"conservative", "balanced", "cautious", "trend_short_factor"}:
        raise ValueError("mode must be conservative, balanced, cautious, or trend_short_factor")
    rows = list(adaptation_report.get("strategies", []))
    allowed = sorted(
        row["reason"]
        for row in rows
        if row.get("adaptability_cn") == "强" or (mode in {"balanced", "cautious"} and _balanced_allows(row))
    )
    if mode == "trend_short_factor":
        allowed = sorted(set(allowed) | {"trend_short"})
    blocked = sorted(row["reason"] for row in rows if row["reason"] not in set(allowed))
    reason_risk_multipliers = {
        row["reason"]: 0.35
        for row in rows
        if mode == "cautious" and row["reason"] in set(allowed) and row.get("adaptability_cn") != "强"
    }
    if mode == "trend_short_factor" and "trend_short" in set(allowed):
        reason_risk_multipliers["trend_short"] = 0.35
    reason_allowed_regimes = {
        reason: _default_allowed_regimes_for_reason(reason)
        for reason in allowed
        if _default_allowed_regimes_for_reason(reason)
    }
    return {
        "mode": mode,
        "allowed_reasons": tuple(allowed),
        "blocked_reasons": tuple(blocked),
        "reason_risk_multipliers": reason_risk_multipliers,
        "trend_short_factor_gate_enabled": mode == "trend_short_factor",
        "reason_allowed_regimes": reason_allowed_regimes,
        "reason_allowed_regimes_cn": {
            reason: tuple(_REGIME_CN.get(regime, regime) for regime in regimes)
            for reason, regimes in reason_allowed_regimes.items()
        },
        "allowed_reasons_cn": [translate_reason(reason) for reason in allowed],
        "blocked_reasons_cn": [translate_reason(reason) for reason in blocked],
    }


def apply_router_profile(config: BacktestConfig, profile: dict) -> BacktestConfig:
    reason_risk_multipliers = dict(config.reason_risk_multipliers)
    reason_risk_multipliers.update(profile.get("reason_risk_multipliers", {}))
    reason_allowed_regimes = dict(config.router_reason_allowed_regimes)
    reason_allowed_regimes.update(profile.get("reason_allowed_regimes", {}))
    return replace(
        config,
        enable_dynamic_strategy_router=True,
        router_allowed_reasons=tuple(profile.get("allowed_reasons", ())),
        router_blocked_reasons=tuple(profile.get("blocked_reasons", ())),
        router_reason_allowed_regimes=reason_allowed_regimes,
        router_trend_short_factor_gate_enabled=bool(profile.get("trend_short_factor_gate_enabled", False)),
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
    threshold_profiles = (
        {
            "transition_long_pullback_min_volume_ratio": 1.3,
            "transition_long_volume_min_volume_ratio": 1.35,
            "transition_long_volume_rsi_max": 65.0,
        },
        {
            "transition_long_pullback_min_volume_ratio": 1.15,
            "transition_long_volume_min_volume_ratio": 1.25,
            "transition_long_volume_rsi_max": 68.0,
        },
        {
            "transition_long_pullback_min_volume_ratio": 1.45,
            "transition_long_volume_min_volume_ratio": 1.5,
            "transition_long_volume_rsi_max": 62.0,
        },
    )
    consolidation_profiles = (
        {"transition_long_consolidation_enabled": False},
        {
            "transition_long_consolidation_enabled": True,
            "transition_long_consolidation_lookback_bars": 8,
            "transition_long_consolidation_max_range_atr": 1.0,
            "transition_long_consolidation_min_volume_ratio": 1.15,
        },
    )
    for item in ranked_configs:
        base = item["config"]
        variant_index = 1
        for min_score in min_scores:
            for move_filter in move_filters:
                for risk_multiplier in risk_multipliers:
                    for threshold_profile in threshold_profiles:
                        for consolidation_profile in consolidation_profiles:
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
                                        **threshold_profile,
                                        **consolidation_profile,
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
        "router_rejections": result.get("router_rejections", {}),
    }


def _reason_trade_share(result: dict) -> dict[str, float]:
    by_reason = result.get("by_reason") or {}
    total = sum(float(item.get("trades", 0.0)) for item in by_reason.values())
    if total <= 0:
        return {}
    return {reason: float(item.get("trades", 0.0)) / total for reason, item in by_reason.items()}


def _reason_similarity(result: dict, baseline_result: dict | None) -> float:
    if not baseline_result:
        return 0.0
    left = _reason_trade_share(result)
    right = _reason_trade_share(baseline_result)
    if not left or not right:
        return 0.0
    reasons = set(left) | set(right)
    distance = sum(abs(left.get(reason, 0.0) - right.get(reason, 0.0)) for reason in reasons) / 2.0
    return max(0.0, 1.0 - distance)


def score_prefilter_result(result: dict, baseline_result: dict | None = None) -> float:
    pnl = float(result.get("pnl", 0.0))
    drawdown = float(result.get("max_drawdown_pct", 0.0))
    trades = int(result.get("trades", 0) or 0)
    trade_quality = min(1.0, trades / 8.0)
    sparse_penalty = max(0.0, (3 - trades) * 1.5)
    similarity = _reason_similarity(result, baseline_result)
    return pnl - drawdown * 0.08 + trade_quality * 1.2 + similarity * 1.0 - sparse_penalty


def rank_prefilter_results(
    results: list[dict],
    limit: int,
    always_keep_ranks: tuple[str, ...] = (),
    baseline_result: dict | None = None,
) -> list[dict]:
    ranked = sorted(
        results,
        key=lambda item: (
            score_prefilter_result(item["result"], baseline_result=baseline_result),
            -float(item["result"].get("max_drawdown_pct", 999.0)),
            int(item["result"].get("trades", 0)),
        ),
        reverse=True,
    )
    if limit <= 0 and not always_keep_ranks:
        return ranked
    keep = set(always_keep_ranks)
    selected: list[dict] = []
    selected_ranks: set[str] = set()
    for item in results:
        if item["rank"] in keep:
            selected.append(item)
            selected_ranks.add(item["rank"])
    for item in ranked:
        if item["rank"] in selected_ranks:
            continue
        if limit > 0 and len(selected) >= limit + len(keep):
            break
        selected.append(item)
        selected_ranks.add(item["rank"])
    return selected


def rank_aggregate_prefilter_results(
    by_window: dict[int, list[dict]],
    limit: int,
    always_keep_ranks: tuple[str, ...] = (),
) -> list[dict]:
    ranks: dict[str, dict] = {}
    scores: dict[str, float] = {}
    for _days, results in by_window.items():
        baseline_result = next((item["result"] for item in results if item["rank"] in set(always_keep_ranks)), None)
        for item in results:
            rank = item["rank"]
            ranks.setdefault(rank, {"rank": rank, "result": item["result"], "window_results": {}})
            ranks[rank]["window_results"][_days] = item["result"]
            score = score_prefilter_result(item["result"], baseline_result=baseline_result)
            if float(item["result"].get("pnl", 0.0)) < 0:
                score -= 3.0
            if float(item["result"].get("max_drawdown_pct", 0.0)) > 25.0:
                score -= 2.0
            scores[rank] = scores.get(rank, 0.0) + score
    ranked = sorted(
        ranks.values(),
        key=lambda item: (
            scores.get(item["rank"], 0.0),
            -max(float(result.get("max_drawdown_pct", 0.0)) for result in item["window_results"].values()),
        ),
        reverse=True,
    )
    keep = set(always_keep_ranks)
    selected: list[dict] = []
    selected_ranks: set[str] = set()
    for item in ranked:
        if item["rank"] in keep:
            selected.append(item)
            selected_ranks.add(item["rank"])
    for item in ranked:
        if item["rank"] in selected_ranks:
            continue
        if limit > 0 and len(selected) >= limit + len(keep):
            break
        selected.append(item)
        selected_ranks.add(item["rank"])
    return selected


def parse_prefilter_days(raw: str | int) -> tuple[int, ...]:
    if isinstance(raw, int):
        return (raw,) if raw > 0 else ()
    return tuple(int(part.strip()) for part in str(raw).split(",") if part.strip() and int(part.strip()) > 0)


def prefilter_ranked_configs(
    market: dict,
    ranked_configs: list[dict],
    profile: dict,
    *,
    days: tuple[int, ...],
    start_equity: float,
    top: int,
) -> tuple[list[dict], dict]:
    by_window: dict[int, list[dict]] = {}
    configs_by_rank = {item["rank"]: item for item in ranked_configs}
    always_keep = tuple(item["rank"] for item in ranked_configs if "source_rank" not in item)
    for day_count in days:
        results: list[dict] = []
        for item in ranked_configs:
            config = apply_router_profile(replace(item["config"], start_equity=start_equity), profile)
            result = Backtester(config).run(market, days=day_count)
            results.append({"rank": item["rank"], "result": compact_result(result)})
        by_window[day_count] = results
    selected = rank_aggregate_prefilter_results(by_window, top, always_keep_ranks=always_keep)
    return [configs_by_rank[item["rank"]] for item in selected], {
        "days": list(days),
        "top": top,
        "searched": len(ranked_configs),
        "selected": selected,
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
    parser.add_argument("--prefilter-days", default="0")
    parser.add_argument("--prefilter-top", type=int, default=0)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--mode", choices=("conservative", "balanced", "cautious", "trend_short_factor"), default="conservative")
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
    prefilter = None
    prefilter_days = parse_prefilter_days(args.prefilter_days)
    if prefilter_days and args.prefilter_top > 0:
        ranked, prefilter = prefilter_ranked_configs(
            market=market,
            ranked_configs=ranked,
            profile=profile,
            days=prefilter_days,
            start_equity=args.start_equity,
            top=args.prefilter_top,
        )
    report = run_router_experiment(
        market=market,
        ranked_configs=ranked,
        profile=profile,
        days=args.days,
        start_equity=args.start_equity,
    )
    if prefilter is not None:
        report["prefilter"] = prefilter
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
