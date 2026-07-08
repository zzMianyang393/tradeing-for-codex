from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from goal_search import market_feature_flags_for_configs
from market import FeatureBar, load_market
from monthly_goal import _load_ranked_configs, compact_month_result, parse_month_targets
from staged_goal import filter_market_range


DAY_MS = 86_400_000
MANIFEST_FIELDS = (
    "risk_per_trade",
    "max_margin_fraction",
    "max_total_margin_fraction",
    "stop_atr",
    "take_profit_atr",
    "trailing_atr",
    "max_hold_bars",
    "range_take_profit_atr",
    "range_trailing_atr",
    "cooldown_bars",
    "loss_cooldown_bars",
    "max_positions",
    "active_symbol_limit",
    "enable_attack_module",
    "enable_micro_momentum_module",
    "enable_funding_module",
    "enable_open_interest_module",
    "enable_trade_flow_module",
    "enable_order_book_module",
    "enable_long_window_aggressive_profile",
    "enabled_regimes",
)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def historical_windows(
    timeline: list[int],
    source_start_ts: int,
    window_days: int = 30,
    step_days: int = 30,
    lookback_days: int = 365,
) -> list[tuple[int, int]]:
    """Build fixed historical test windows before the optimized source sample."""
    if not timeline:
        return []
    earliest = timeline[0]
    latest_allowed_start = source_start_ts - window_days * DAY_MS
    lookback_start = source_start_ts - lookback_days * DAY_MS
    start = max(earliest, lookback_start)
    end_limit = min(source_start_ts, timeline[-1])
    windows: list[tuple[int, int]] = []
    cursor = start
    while cursor <= latest_allowed_start and cursor + window_days * DAY_MS <= end_limit:
        windows.append((cursor, cursor + window_days * DAY_MS))
        cursor += step_days * DAY_MS
    return windows


def build_strategy_targets(report: dict, months: list[int]) -> list[dict]:
    month_set = set(months)
    targets: list[dict] = []
    for item in report.get("months", []):
        if int(item["month"]) not in month_set:
            continue
        result = item["result"]
        targets.append(
            {
                "month": int(item["month"]),
                "rank": item["rank"],
                "regime": result.get("dominant_regime"),
                "reason": result.get("dominant_reason"),
                "target_return_pct": float(result.get("return_pct", 0.0)),
                "target_drawdown_pct": float(result.get("max_drawdown_pct", 0.0)),
                "target_win_rate": float(result.get("win_rate", 0.0)),
                "target_trades": int(result.get("trades", 0)),
            }
        )
    return targets


def resolve_target_config(rank: str, configs: list[dict]) -> BacktestConfig:
    for item in configs:
        if item["rank"] == rank:
            return item["config"]
    raise ValueError(f"rank {rank!r} not found in loaded configs")


def _jsonable(value):
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in sorted(value.items())}
    return value


def config_manifest(config: BacktestConfig) -> dict:
    return {field: _jsonable(getattr(config, field)) for field in MANIFEST_FIELDS if hasattr(config, field)}


def config_fingerprint(config: BacktestConfig) -> str:
    payload = json.dumps(config_manifest(config), sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def build_strategy_manifest(monthly_report: dict, configs: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for month in monthly_report.get("months", []):
        config = resolve_target_config(month["rank"], configs)
        fingerprint = config_fingerprint(config)
        result = month["result"]
        rows.append(
            {
                "month": int(month["month"]),
                "rank": month["rank"],
                "regime": result.get("dominant_regime"),
                "reason": result.get("dominant_reason"),
                "parameter_group": fingerprint,
                "key_parameters": config_manifest(config),
                "return_pct": result.get("return_pct"),
                "max_drawdown_pct": result.get("max_drawdown_pct"),
                "win_rate": result.get("win_rate"),
                "trades": result.get("trades"),
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["parameter_group"]] = counts.get(row["parameter_group"], 0) + 1
    for row in rows:
        row["same_parameters_as_other_month"] = counts[row["parameter_group"]] > 1
    return rows


def _same_regime(target: dict, result: dict) -> bool:
    return result.get("dominant_regime") == target.get("regime")


def _same_reason(target: dict, result: dict) -> bool:
    return _same_regime(target, result) and result.get("dominant_reason") == target.get("reason")


def judge_historical_support(
    target: dict,
    validations: list[dict],
    min_similar_windows: int = 3,
    min_positive_ratio: float = 0.5,
    min_decay_ratio: float = 0.25,
) -> dict:
    same_regime = [item for item in validations if _same_regime(target, item)]
    same_reason = [item for item in validations if _same_reason(target, item)]
    comparable = same_reason or same_regime
    returns = [float(item.get("return_pct", 0.0)) for item in comparable]
    pnl_values = [float(item.get("pnl", 0.0)) for item in comparable]
    drawdowns = [float(item.get("max_drawdown_pct", 0.0)) for item in comparable]
    median_return = _median(returns)
    target_return = float(target.get("target_return_pct", 0.0))
    decay = round(median_return / target_return, 4) if target_return else 0.0
    positive = sum(1 for pnl in pnl_values if pnl > 0)
    positive_ratio = positive / len(comparable) if comparable else 0.0
    median_drawdown = _median(drawdowns)

    reasons: list[str] = []
    if len(comparable) < min_similar_windows:
        reasons.append("not enough similar historical windows")
    if comparable and positive_ratio < min_positive_ratio:
        reasons.append("less than half of similar windows are profitable")
    if target_return > 0 and decay < min_decay_ratio:
        reasons.append("same-regime median return decays too much")
    if comparable and median_return <= 0:
        reasons.append("similar-window median return is non-positive")
    if comparable and median_drawdown > float(target.get("target_drawdown_pct", 0.0)) * 1.25:
        reasons.append("historical drawdown expands beyond target")

    risk_level = "low"
    if len(reasons) >= 2:
        risk_level = "high"
    elif reasons:
        risk_level = "medium"

    return {
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "validation_windows": len(validations),
        "same_regime_windows": len(same_regime),
        "same_reason_windows": len(same_reason),
        "similar_windows": len(comparable),
        "similar_positive": positive,
        "similar_positive_ratio": round(positive_ratio, 4),
        "similar_median_return_pct": round(median_return, 4),
        "similar_median_drawdown_pct": round(median_drawdown, 4),
        "decay_ratio": decay,
    }


def validate_target_on_history(
    market: dict[str, list[FeatureBar]],
    target: dict,
    config: BacktestConfig,
    windows: list[tuple[int, int]],
    start_equity: float,
) -> dict:
    validations: list[dict] = []
    for index, (start_ts, end_ts) in enumerate(windows, start=1):
        window_market = filter_market_range(market, start_ts, end_ts)
        if not window_market:
            continue
        result = Backtester(replace(config, start_equity=start_equity)).run(window_market, days=None)
        compact = compact_month_result(result)
        compact["window"] = index
        compact["start_ts"] = start_ts
        compact["end_ts"] = end_ts
        validations.append(compact)
    support = judge_historical_support(target, validations)
    return {**target, "support": support, "validations": validations}


def source_sample_start_ts(timeline: list[int], source_total_days: int = 365) -> int:
    if not timeline:
        return 0
    return timeline[-1] - source_total_days * DAY_MS


def run_historical_regime_validation(
    market: dict[str, list[FeatureBar]],
    monthly_report: dict,
    configs: list[dict],
    target_months: list[int],
    window_days: int,
    step_days: int,
    lookback_days: int,
    source_total_days: int,
    start_equity: float,
) -> dict:
    timeline = sorted({bar.ts for bars in market.values() for bar in bars})
    source_start = source_sample_start_ts(timeline, source_total_days=source_total_days)
    windows = historical_windows(
        timeline,
        source_start_ts=source_start,
        window_days=window_days,
        step_days=step_days,
        lookback_days=lookback_days,
    )
    targets = build_strategy_targets(monthly_report, target_months)
    rows = []
    for target in targets:
        config = resolve_target_config(target["rank"], configs)
        rows.append(validate_target_on_history(market, target, config, windows, start_equity=start_equity))
    return {
        "source_total_days": source_total_days,
        "historical_window_days": window_days,
        "historical_step_days": step_days,
        "lookback_days": lookback_days,
        "source_start_ts": source_start,
        "windows": [{"start_ts": start, "end_ts": end} for start, end in windows],
        "targets": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate fixed monthly strategies on older similar-regime windows.")
    parser.add_argument("monthly_report", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--reports", required=True)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--months", default="")
    parser.add_argument("--window-days", type=int, default=30)
    parser.add_argument("--step-days", type=int, default=15)
    parser.add_argument("--lookback-days", type=int, default=900)
    parser.add_argument("--source-total-days", type=int, default=365)
    parser.add_argument("--start-equity", type=float, default=10.0)
    parser.add_argument("--manifest-only", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("reports/historical_regime_validation.json"))
    args = parser.parse_args()

    monthly_report = json.loads(args.monthly_report.read_text(encoding="utf-8"))
    report_paths = tuple(Path(part.strip()) for part in args.reports.split(",") if part.strip())
    configs = _load_ranked_configs(report_paths, args.limit)
    if args.manifest_only:
        manifest = build_strategy_manifest(monthly_report, configs)
        payload = {"source": str(args.monthly_report), "manifest": manifest}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"saved={args.out}")
        for row in manifest:
            params = row["key_parameters"]
            modules = ",".join(
                name.removeprefix("enable_").removesuffix("_module")
                for name in (
                    "enable_attack_module",
                    "enable_micro_momentum_module",
                    "enable_funding_module",
                    "enable_open_interest_module",
                    "enable_trade_flow_module",
                    "enable_order_book_module",
                )
                if params.get(name)
            ) or "base"
            print(
                f"m{row['month']:02d} group={row['parameter_group']} rank={row['rank']} "
                f"regime={row['regime']} reason={row['reason']} modules={modules} "
                f"risk={params.get('risk_per_trade')} margin={params.get('max_margin_fraction')}/"
                f"{params.get('max_total_margin_fraction')} tp={params.get('take_profit_atr')} "
                f"stop={params.get('stop_atr')} trail={params.get('trailing_atr')} "
                f"reuse={row['same_parameters_as_other_month']}"
            )
        return
    target_months = parse_month_targets(args.months) or [
        int(item["month"])
        for item in monthly_report.get("months", [])
        if item.get("overfit_risk", {}).get("level") in {"medium", "high"}
    ]
    market = load_market(
        args.data,
        BacktestConfig().timeframe_minutes,
        **market_feature_flags_for_configs([item["config"] for item in configs]),
    )
    report = run_historical_regime_validation(
        market=market,
        monthly_report=monthly_report,
        configs=configs,
        target_months=target_months,
        window_days=args.window_days,
        step_days=args.step_days,
        lookback_days=args.lookback_days,
        source_total_days=args.source_total_days,
        start_equity=args.start_equity,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    print(f"history_windows={len(report['windows'])} targets={len(report['targets'])}")
    for row in report["targets"]:
        support = row["support"]
        print(
            f"m{row['month']:02d} rank={row['rank']} regime={row['regime']} reason={row['reason']} "
            f"risk={support['risk_level']} similar={support['similar_positive']}/{support['similar_windows']} "
            f"median={support['similar_median_return_pct']:.2f}% decay={support['decay_ratio']:.2f} "
            f"reasons={';'.join(support['risk_reasons'])}"
        )


if __name__ == "__main__":
    main()
