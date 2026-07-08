from __future__ import annotations

import argparse
import json
from pathlib import Path

from monthly_goal import assess_overfit_risk, parse_month_targets, results_by_rank


def strategy_label(month: dict) -> str:
    result = month["result"]
    return f"{month['rank']}|{result.get('dominant_regime')}|{result.get('dominant_reason')}"


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def adjacent_validation_results(report: dict, rank: str, target_month: int, radius: int = 1) -> list[dict]:
    grouped = results_by_rank(report)
    return [
        item
        for item in grouped.get(rank, [])
        if item["month"] != target_month and abs(int(item["month"]) - target_month) <= radius
    ]


def decay_ratio(target_return_pct: float, validation_returns_pct: list[float]) -> float:
    if not validation_returns_pct or target_return_pct == 0:
        return 0.0
    return round(_median(validation_returns_pct) / target_return_pct, 4)


def _risk_from_checks(base_level: str, reasons: list[str]) -> str:
    if base_level == "high" or len(reasons) >= 2:
        return "high"
    if base_level == "medium" or reasons:
        return "medium"
    return "low"


def build_overfit_matrix(report: dict, target_months: list[int], adjacent_radius: int = 1) -> list[dict]:
    rows: list[dict] = []
    month_by_number = {int(item["month"]): item for item in report.get("months", [])}
    grouped = results_by_rank(report)
    for month_number in target_months:
        month = month_by_number[month_number]
        target_result = month["result"]
        validation = [
            item["result"]
            for item in grouped.get(month["rank"], [])
            if int(item["month"]) != month_number
        ]
        adjacent = adjacent_validation_results(report, month["rank"], month_number, radius=adjacent_radius)
        base_risk = assess_overfit_risk(target_result, validation)
        adjacent_returns = [float(item["result"].get("return_pct", 0.0)) for item in adjacent]
        validation_returns = [float(item.get("return_pct", 0.0)) for item in validation]
        reasons = list(base_risk["reasons"])
        adjacent_median = _median(adjacent_returns)
        if adjacent and adjacent_median < max(3.0, float(target_result.get("return_pct", 0.0)) * 0.2):
            reasons.append("adjacent validation is weak")
        row = {
            "month": month_number,
            "strategy": strategy_label(month),
            "qualified": month.get("audit", {}).get("qualified", False),
            "target_return_pct": round(float(target_result.get("return_pct", 0.0)), 4),
            "target_drawdown_pct": round(float(target_result.get("max_drawdown_pct", 0.0)), 4),
            "target_win_rate": round(float(target_result.get("win_rate", 0.0)), 4),
            "target_trades": int(target_result.get("trades", 0)),
            "same_regime_median_return_pct": base_risk["same_regime_median_return_pct"],
            "validation_positive": base_risk["positive_validation_windows"],
            "validation_windows": base_risk["validation_windows"],
            "adjacent_median_return_pct": round(adjacent_median, 4),
            "decay_ratio": decay_ratio(float(target_result.get("return_pct", 0.0)), validation_returns),
            "risk_level": _risk_from_checks(base_risk["level"], reasons),
            "risk_reasons": reasons,
        }
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build overfitting test matrix from a monthly goal report.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--months", default="")
    parser.add_argument("--adjacent-radius", type=int, default=1)
    parser.add_argument("--out", type=Path, default=Path("reports/overfit_matrix.json"))
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    target_months = parse_month_targets(args.months)
    if not target_months:
        target_months = [
            int(item["month"])
            for item in report.get("months", [])
            if "overfit_risk" in item
        ]
    matrix = build_overfit_matrix(report, target_months, adjacent_radius=args.adjacent_radius)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"source": str(args.report), "targets": target_months, "matrix": matrix}, indent=2), encoding="utf-8")
    print(f"saved={args.out}")
    for row in matrix:
        print(
            f"m{row['month']:02d} risk={row['risk_level']} strategy={row['strategy']} "
            f"ret={row['target_return_pct']:.2f}% dd={row['target_drawdown_pct']:.2f}% "
            f"same_regime_median={row['same_regime_median_return_pct']} "
            f"adjacent_median={row['adjacent_median_return_pct']} "
            f"validation={row['validation_positive']}/{row['validation_windows']} "
            f"reasons={';'.join(row['risk_reasons'])}"
        )


if __name__ == "__main__":
    main()
