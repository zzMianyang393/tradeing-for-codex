from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig, SymbolRisk
from goal_search import audit_goal_results, market_feature_flags_for_configs, mutate_seed_config, restore_config_payload
from market import FeatureBar, load_market


@dataclass(frozen=True)
class StageSpec:
    name: str
    days: int
    config: BacktestConfig


def split_stage_ranges(timeline: list[int], total_days: int, stages: tuple[int, ...]) -> list[tuple[int, int]]:
    if not timeline:
        return []
    if sum(stages) != total_days:
        raise ValueError("stage days must add up to total days")
    end_ts = timeline[-1]
    start_ts = end_ts - total_days * 86_400_000
    ranges: list[tuple[int, int]] = []
    cursor = start_ts
    for days in stages:
        next_cursor = cursor + days * 86_400_000
        ranges.append((cursor, next_cursor))
        cursor = next_cursor
    return ranges


def config_for_stage(stage: StageSpec, start_equity: float) -> BacktestConfig:
    return replace(stage.config, start_equity=start_equity)


def build_stage_specs(sprint: BacktestConfig, growth: BacktestConfig, order: str) -> tuple[StageSpec, ...]:
    if order == "sprint-first":
        return (StageSpec("sprint", 30, sprint), StageSpec("growth", 335, growth))
    if order == "growth-first":
        return (StageSpec("growth", 335, growth), StageSpec("sprint", 30, sprint))
    raise ValueError("order must be sprint-first or growth-first")


def build_multi_sprint_stage_specs(
    sprint: BacktestConfig,
    growth: BacktestConfig,
    total_days: int,
    sprint_days: int,
    sprint_count: int,
) -> tuple[StageSpec, ...]:
    if sprint_count < 1:
        raise ValueError("sprint_count must be positive")
    growth_days = total_days - sprint_days * sprint_count
    if growth_days <= 0:
        raise ValueError("sprint stages must leave at least one growth day")
    return (StageSpec("growth", growth_days, growth),) + tuple(
        StageSpec(f"sprint_{index}", sprint_days, sprint)
        for index in range(1, sprint_count + 1)
    )


def filter_market_range(
    market: dict[str, list[FeatureBar]],
    start_ts: int,
    end_ts: int,
) -> dict[str, list[FeatureBar]]:
    filtered: dict[str, list[FeatureBar]] = {}
    for symbol, bars in market.items():
        kept = [bar for bar in bars if start_ts <= bar.ts <= end_ts]
        if kept:
            filtered[symbol] = kept
    return filtered


def aggregate_stage_results(start_equity: float, stage_results: list[dict]) -> dict:
    end_equity = float(stage_results[-1]["end_equity"]) if stage_results else start_equity
    return {
        "start_equity": round(start_equity, 4),
        "end_equity": round(end_equity, 4),
        "pnl": round(end_equity - start_equity, 4),
        "return_pct": round((end_equity - start_equity) / start_equity * 100.0, 4) if start_equity else 0.0,
        "trades": sum(int(stage.get("trades", 0)) for stage in stage_results),
        "max_drawdown_pct": max((float(stage.get("max_drawdown_pct", 0.0)) for stage in stage_results), default=0.0),
        "stages": stage_results,
    }


def load_config_from_report(path: Path, rank: int = 1) -> BacktestConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ranked = load_top_configs_from_report_payload(payload, limit=rank)
    if ranked:
        return ranked[rank - 1]["config"]
    raw_config = payload.get("config")
    if not isinstance(raw_config, dict):
        raise ValueError(f"{path} has no config")
    base = BacktestConfig(validation_target_returns={}, validation_target_win_rate=0.0)
    return restore_config_payload(raw_config, base)


def load_top_configs_from_report_payload(payload: dict, limit: int) -> list[dict]:
    base = BacktestConfig(validation_target_returns={}, validation_target_win_rate=0.0)
    ranked: list[dict] = []
    for index, item in enumerate(payload.get("top", [])[:limit], start=1):
        raw_config = item.get("full_config") or item.get("config")
        if not isinstance(raw_config, dict):
            continue
        ranked.append({"rank": index, "config": restore_config_payload(raw_config, base)})
    return ranked


def load_top_configs_from_report(path: Path, limit: int) -> list[dict]:
    return load_top_configs_from_report_payload(json.loads(path.read_text(encoding="utf-8")), limit=limit)


def staged_market_feature_flags(sprint_configs: list[dict], growth_configs: list[dict]) -> dict[str, bool]:
    return market_feature_flags_for_configs(
        [item["config"] for item in sprint_configs] + [item["config"] for item in growth_configs]
    )


def effective_grid_limits(grid_limit: int, sprint_grid_limit: int, growth_grid_limit: int) -> tuple[int, int]:
    return sprint_grid_limit or grid_limit, growth_grid_limit or grid_limit


def is_grid_search_requested(grid_limit: int, sprint_grid_limit: int, growth_grid_limit: int) -> bool:
    return bool(grid_limit or sprint_grid_limit or growth_grid_limit)


def expand_ranked_configs_with_mutations(
    ranked_configs: list[dict],
    seed: int,
    mutations_per_config: int,
) -> list[dict]:
    if mutations_per_config <= 0:
        return ranked_configs
    import random

    rng = random.Random(seed)
    expanded = list(ranked_configs)
    for item in ranked_configs:
        for mutation_index in range(1, mutations_per_config + 1):
            expanded.append(
                {
                    "rank": f"{item['rank']}m{mutation_index}",
                    "source_rank": item["rank"],
                    "mutation": mutation_index,
                    "config": mutate_seed_config(item["config"], rng),
                }
            )
    return expanded


def run_staged_report(
    market: dict[str, list[FeatureBar]],
    stages: tuple[StageSpec, ...],
    total_days: int,
    start_equity: float,
) -> dict:
    timeline = sorted({bar.ts for bars in market.values() for bar in bars})
    ranges = split_stage_ranges(timeline, total_days=total_days, stages=tuple(stage.days for stage in stages))
    equity = start_equity
    stage_results: list[dict] = []
    for stage, (start_ts, end_ts) in zip(stages, ranges):
        stage_market = filter_market_range(market, start_ts, end_ts)
        config = config_for_stage(stage, equity)
        result = Backtester(config).run(stage_market, days=None)
        result = dict(result)
        result["name"] = stage.name
        result["stage_days"] = stage.days
        result["range"] = {"start_ts": start_ts, "end_ts": end_ts}
        stage_results.append(result)
        equity = float(result["end_equity"])
    report = aggregate_stage_results(start_equity=start_equity, stage_results=stage_results)
    report["target_audit"] = audit_goal_results(
        {total_days: {"pnl": report["pnl"], "max_drawdown_pct": report["max_drawdown_pct"], "trades": report["trades"]}},
        {total_days: 2000.0},
        max_drawdown_pct=95.0,
        min_trades_by_window={total_days: 50},
    )
    return report


def rank_staged_config_pairs(
    sprint_configs: list[dict],
    growth_configs: list[dict],
    orders: tuple[str, ...],
    runner,
    stage_builder=build_stage_specs,
) -> list[dict]:
    reports: list[dict] = []
    for sprint_item in sprint_configs:
        for growth_item in growth_configs:
            for order in orders:
                stages = stage_builder(sprint_item["config"], growth_item["config"], order)
                report = dict(runner(stages, order))
                report["sprint_rank"] = sprint_item["rank"]
                report["growth_rank"] = growth_item["rank"]
                report["order"] = order
                reports.append(report)
    reports.sort(
        key=lambda item: (
            float(item.get("pnl", 0.0)),
            int(item.get("trades", 0)),
            -float(item.get("max_drawdown_pct", 0.0)),
        ),
        reverse=True,
    )
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description="Run staged 10U goal backtest.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--sprint-report", type=Path, default=Path("reports/goal_30d_fullseed_40.json"))
    parser.add_argument("--growth-report", type=Path, default=Path("reports/goal_365d_fullseed_40.json"))
    parser.add_argument("--sprint-rank", type=int, default=1)
    parser.add_argument("--growth-rank", type=int, default=1)
    parser.add_argument("--order", choices=("sprint-first", "growth-first"), default="growth-first")
    parser.add_argument("--grid-limit", type=int, default=0)
    parser.add_argument("--sprint-grid-limit", type=int, default=0)
    parser.add_argument("--growth-grid-limit", type=int, default=0)
    parser.add_argument("--sprint-mutations", type=int, default=0)
    parser.add_argument("--growth-mutations", type=int, default=0)
    parser.add_argument("--sprint-count", type=int, default=1)
    parser.add_argument("--sprint-days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260708)
    parser.add_argument("--out", type=Path, default=Path("reports/staged_goal_latest.json"))
    args = parser.parse_args()

    sprint_limit, growth_limit = effective_grid_limits(args.grid_limit, args.sprint_grid_limit, args.growth_grid_limit)
    sprint_configs = load_top_configs_from_report(args.sprint_report, sprint_limit or args.sprint_rank)
    growth_configs = load_top_configs_from_report(args.growth_report, growth_limit or args.growth_rank)
    sprint_configs = expand_ranked_configs_with_mutations(sprint_configs, args.seed, args.sprint_mutations)
    growth_configs = expand_ranked_configs_with_mutations(growth_configs, args.seed + 10_000, args.growth_mutations)
    sprint = sprint_configs[0]["config"] if args.grid_limit else load_config_from_report(args.sprint_report, args.sprint_rank)
    growth = growth_configs[0]["config"] if args.grid_limit else load_config_from_report(args.growth_report, args.growth_rank)
    market = load_market(
        args.data,
        sprint.timeframe_minutes,
        **staged_market_feature_flags(sprint_configs, growth_configs),
    )
    grid_requested = is_grid_search_requested(args.grid_limit, args.sprint_grid_limit, args.growth_grid_limit)
    if grid_requested:
        def grid_stage_builder(sprint_config: BacktestConfig, growth_config: BacktestConfig, order: str) -> tuple[StageSpec, ...]:
            if order == "growth-first" and args.sprint_count > 1:
                return build_multi_sprint_stage_specs(
                    sprint_config,
                    growth_config,
                    total_days=365,
                    sprint_days=args.sprint_days,
                    sprint_count=args.sprint_count,
                )
            return build_stage_specs(sprint_config, growth_config, order)

        reports = rank_staged_config_pairs(
            sprint_configs=sprint_configs,
            growth_configs=growth_configs,
            orders=("sprint-first", "growth-first"),
            runner=lambda stages, order: run_staged_report(
                market=market,
                stages=stages,
                total_days=365,
                start_equity=10.0,
            ),
            stage_builder=grid_stage_builder,
        )
        report = {"best": reports[0], "top": reports[: min(20, len(reports))], "searched": len(reports)}
    else:
        stages = (
            build_multi_sprint_stage_specs(sprint, growth, total_days=365, sprint_days=args.sprint_days, sprint_count=args.sprint_count)
            if args.order == "growth-first" and args.sprint_count > 1
            else build_stage_specs(sprint, growth, args.order)
        )
        report = run_staged_report(
            market=market,
            stages=stages,
            total_days=365,
            start_equity=10.0,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    if grid_requested:
        best = report["best"]
        print(
            f"best staged 365d equity={best['end_equity']:.4f} pnl={best['pnl']:.4f} "
            f"return={best['return_pct']:.2f}% trades={best['trades']} dd={best['max_drawdown_pct']:.2f}% "
            f"order={best['order']} sprint_rank={best['sprint_rank']} growth_rank={best['growth_rank']}"
        )
        return
    print(
        f"staged 365d equity={report['end_equity']:.4f} pnl={report['pnl']:.4f} "
        f"return={report['return_pct']:.2f}% trades={report['trades']} dd={report['max_drawdown_pct']:.2f}%"
    )


if __name__ == "__main__":
    main()
