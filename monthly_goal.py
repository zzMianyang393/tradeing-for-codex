from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from goal_search import market_feature_flags_for_configs
from market import FeatureBar, load_market
from staged_goal import filter_market_range, load_top_configs_from_report_payload


def month_windows(timeline: list[int], months: int = 12, total_days: int = 365) -> list[tuple[int, int]]:
    if not timeline:
        return []
    end_ts = timeline[-1]
    start_ts = end_ts - total_days * 86_400_000
    span = end_ts - start_ts
    windows: list[tuple[int, int]] = []
    cursor = start_ts
    for index in range(months):
        next_cursor = start_ts + span * (index + 1) // months
        windows.append((cursor, next_cursor))
        cursor = next_cursor
    return windows


def parse_month_targets(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _score_month_result(result: dict) -> tuple[float, float, float, int]:
    return (
        float(result.get("pnl", 0.0)),
        -float(result.get("max_drawdown_pct", 999.0)),
        float(result.get("win_rate", 0.0)),
        int(result.get("trades", 0)),
    )


def select_month_winner(candidates: list[dict]) -> dict:
    return max(candidates, key=lambda item: _score_month_result(item["result"]))


def select_qualified_month_winner(
    candidates: list[dict],
    min_pnl: float,
    max_drawdown_pct: float,
    min_win_rate: float,
    min_trades: int,
) -> dict:
    qualified = [
        item
        for item in candidates
        if classify_month(
            item["result"],
            min_pnl=min_pnl,
            max_drawdown_pct=max_drawdown_pct,
            min_win_rate=min_win_rate,
            min_trades=min_trades,
        )["qualified"]
    ]
    return select_month_winner(qualified or candidates)


def classify_month(
    result: dict,
    min_pnl: float,
    max_drawdown_pct: float,
    min_win_rate: float,
    min_trades: int,
) -> dict:
    failures: list[str] = []
    pnl = float(result.get("pnl", 0.0))
    drawdown = float(result.get("max_drawdown_pct", 0.0))
    win_rate = float(result.get("win_rate", 0.0))
    trades = int(result.get("trades", 0))
    if pnl < min_pnl:
        failures.append(f"pnl {pnl:g} < {min_pnl:g}")
    if drawdown > max_drawdown_pct:
        failures.append(f"drawdown {drawdown:.2f}% > {max_drawdown_pct:.2f}%")
    if win_rate < min_win_rate:
        failures.append(f"win_rate {win_rate:.2%} < {min_win_rate:.2%}")
    if trades < min_trades:
        failures.append(f"trades {trades} < {min_trades}")
    return {"qualified": not failures, "failures": failures}


def _dominant_bucket(buckets: dict) -> str | None:
    if not buckets:
        return None
    return max(
        buckets.items(),
        key=lambda item: (float(item[1].get("pnl", 0.0)), int(item[1].get("trades", 0))),
    )[0]


def compact_month_result(result: dict) -> dict:
    keys = ("pnl", "return_pct", "max_drawdown_pct", "win_rate", "trades", "from", "to")
    compact = {key: result[key] for key in keys if key in result}
    compact["dominant_regime"] = _dominant_bucket(result.get("by_regime", {}))
    compact["dominant_reason"] = _dominant_bucket(result.get("by_reason", {}))
    compact["by_regime"] = result.get("by_regime", {})
    compact["by_reason"] = result.get("by_reason", {})
    return compact


def select_target_months(report: dict) -> list[int]:
    return [
        int(item["month"])
        for item in report.get("months", [])
        if not item.get("audit", {}).get("qualified", False)
    ]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def assess_overfit_risk(target_result: dict, validation_results: list[dict]) -> dict:
    target_return = float(target_result.get("return_pct", 0.0))
    target_regime = target_result.get("dominant_regime")
    same_regime_returns = [
        float(item.get("return_pct", 0.0))
        for item in validation_results
        if item.get("dominant_regime") == target_regime
    ]
    positive_validations = sum(1 for item in validation_results if float(item.get("pnl", 0.0)) > 0)
    same_regime_median = _median(same_regime_returns)
    reasons: list[str] = []
    if same_regime_returns and same_regime_median < max(3.0, target_return * 0.25):
        reasons.append("same-regime median return is weak")
    if validation_results and positive_validations / len(validation_results) < 0.5:
        reasons.append("less than half of validation windows are profitable")
    if target_return > 0 and same_regime_median <= 0:
        reasons.append("target return is not supported by same-regime validation")
    level = "low"
    if len(reasons) >= 2:
        level = "high"
    elif reasons:
        level = "medium"
    return {
        "level": level,
        "reasons": reasons,
        "same_regime_median_return_pct": round(same_regime_median, 4),
        "positive_validation_windows": positive_validations,
        "validation_windows": len(validation_results),
    }


def results_by_rank(report: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for month in report.get("months", []):
        grouped.setdefault(month["rank"], []).append({"month": month["month"], "result": month["result"]})
        for candidate in month.get("candidates", []):
            grouped.setdefault(candidate["rank"], []).append(
                {"month": month["month"], "result": candidate["result"]}
            )
    return grouped


def annotate_overfit_risks(report: dict, target_months: list[int]) -> dict:
    grouped = results_by_rank(report)
    target_set = set(target_months)
    annotated_months: list[dict] = []
    for month in report.get("months", []):
        item = dict(month)
        if int(item["month"]) in target_set:
            validation_results = [
                entry["result"]
                for entry in grouped.get(item["rank"], [])
                if int(entry["month"]) != int(item["month"])
            ]
            item["overfit_risk"] = assess_overfit_risk(item["result"], validation_results)
        annotated_months.append(item)
    annotated = dict(report)
    annotated["months"] = annotated_months
    return annotated


def _load_ranked_configs(paths: tuple[Path, ...], limit: int) -> list[dict]:
    configs: list[dict] = []
    seen: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in load_top_configs_from_report_payload(payload, limit):
            key = json.dumps(asdict(item["config"]), sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            configs.append({"rank": f"{path.stem}#{item['rank']}", "config": item["config"]})
    return configs


def run_monthly_audit(
    market: dict[str, list[FeatureBar]],
    configs: list[dict],
    months: int,
    total_days: int,
    start_equity: float,
    min_month_pnl: float,
    max_month_drawdown_pct: float,
    min_month_win_rate: float,
    min_month_trades: int,
    keep_candidates: bool = False,
    prefer_qualified: bool = False,
) -> dict:
    timeline = sorted({bar.ts for bars in market.values() for bar in bars})
    windows = month_windows(timeline, months=months, total_days=total_days)
    equity = start_equity
    month_reports: list[dict] = []
    for month_index, (start_ts, end_ts) in enumerate(windows, start=1):
        month_market = filter_market_range(market, start_ts, end_ts)
        candidates: list[dict] = []
        for item in configs:
            config = item["config"]
            result = Backtester(replace(config, start_equity=equity)).run(month_market, days=None)
            candidates.append({"rank": item["rank"], "result": result})
        winner = (
            select_qualified_month_winner(
                candidates,
                min_pnl=min_month_pnl,
                max_drawdown_pct=max_month_drawdown_pct,
                min_win_rate=min_month_win_rate,
                min_trades=min_month_trades,
            )
            if prefer_qualified
            else select_month_winner(candidates)
        )
        compact = compact_month_result(winner["result"])
        audit = classify_month(
            compact,
            min_pnl=min_month_pnl,
            max_drawdown_pct=max_month_drawdown_pct,
            min_win_rate=min_month_win_rate,
            min_trades=min_month_trades,
        )
        equity = float(winner["result"].get("end_equity", equity))
        month_report = {
            "month": month_index,
            "rank": winner["rank"],
            "start_equity": compact.get("start_equity", None),
            "end_equity": round(equity, 4),
            "result": compact,
            "audit": audit,
        }
        if keep_candidates:
            month_report["candidates"] = [
                {"rank": item["rank"], "result": compact_month_result(item["result"])}
                for item in candidates
            ]
        month_reports.append(month_report)
    return {
        "start_equity": start_equity,
        "end_equity": round(equity, 4),
        "pnl": round(equity - start_equity, 4),
        "return_pct": round((equity - start_equity) / start_equity * 100.0, 4),
        "qualified_months": sum(1 for item in month_reports if item["audit"]["qualified"]),
        "months": month_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit 365d goal as 12 monthly strategy windows.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--reports", default="reports/goal_30d_fullseed_40.json,reports/goal_365d_fullseed_40.json")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--total-days", type=int, default=365)
    parser.add_argument("--min-month-pnl", type=float, default=0.0)
    parser.add_argument("--max-month-drawdown-pct", type=float, default=45.0)
    parser.add_argument("--min-month-win-rate", type=float, default=0.48)
    parser.add_argument("--min-month-trades", type=int, default=4)
    parser.add_argument("--start-equity", type=float, default=10.0)
    parser.add_argument("--keep-candidates", action="store_true")
    parser.add_argument("--prefer-qualified", action="store_true")
    parser.add_argument("--target-months", default="")
    parser.add_argument("--out", type=Path, default=Path("reports/monthly_goal_audit.json"))
    args = parser.parse_args()

    report_paths = tuple(Path(part.strip()) for part in args.reports.split(",") if part.strip())
    configs = _load_ranked_configs(report_paths, args.limit)
    market = load_market(
        args.data,
        BacktestConfig().timeframe_minutes,
        **market_feature_flags_for_configs([item["config"] for item in configs]),
    )
    report = run_monthly_audit(
        market=market,
        configs=configs,
        months=args.months,
        total_days=args.total_days,
        start_equity=args.start_equity,
        min_month_pnl=args.min_month_pnl,
        max_month_drawdown_pct=args.max_month_drawdown_pct,
        min_month_win_rate=args.min_month_win_rate,
        min_month_trades=args.min_month_trades,
        keep_candidates=args.keep_candidates,
        prefer_qualified=args.prefer_qualified,
    )
    target_months = parse_month_targets(args.target_months) or select_target_months(report)
    report = annotate_overfit_risks(report, target_months)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    print(
        f"monthly 365d equity={report['end_equity']:.4f} pnl={report['pnl']:.4f} "
        f"return={report['return_pct']:.2f}% qualified={report['qualified_months']}/{args.months}"
    )
    for item in report["months"]:
        result = item["result"]
        print(
            f"m{item['month']:02d} rank={item['rank']} pnl={result['pnl']:.4f} "
            f"ret={result['return_pct']:.2f}% dd={result['max_drawdown_pct']:.2f}% "
            f"win={result['win_rate'] * 100:.2f}% tr={result['trades']} "
            f"regime={result['dominant_regime']} reason={result['dominant_reason']} "
            f"ok={item['audit']['qualified']}"
        )


if __name__ == "__main__":
    main()
