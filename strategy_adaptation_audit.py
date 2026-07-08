from __future__ import annotations

import argparse
import json
from pathlib import Path


REASON_CN = {
    "trend_long": "趋势做多",
    "trend_short": "趋势做空",
    "range_revert_long": "震荡反转做多",
    "range_revert_short": "震荡反转做空",
    "transition_breakout_long": "转换突破做多",
    "transition_breakout_short": "转换突破做空",
    "attack_breakout_long": "攻击突破做多",
    "attack_breakout_short": "攻击突破做空",
    "attack_exhaustion_long": "极端衰竭做多",
    "attack_exhaustion_short": "极端衰竭做空",
    "continuation_long": "延续突破做多",
    "continuation_short": "延续突破做空",
    "micro_momentum_long": "微动量做多",
    "micro_momentum_short": "微动量做空",
    "funding_extreme_long": "资金费率极端做多",
    "funding_extreme_short": "资金费率极端做空",
    "open_interest_breakout_long": "持仓量突破做多",
    "open_interest_breakout_short": "持仓量突破做空",
    "trade_flow_breakout_long": "主动成交突破做多",
    "trade_flow_breakout_short": "主动成交突破做空",
    "order_book_imbalance_long": "盘口失衡做多",
    "order_book_imbalance_short": "盘口失衡做空",
}

REGIME_CN = {
    "uptrend": "上涨趋势",
    "downtrend": "下跌趋势",
    "range": "震荡区间",
    "transition": "趋势转换/突破",
    "continuation": "趋势延续",
    "micro_momentum": "短线动量",
    "funding": "资金费率异常",
    "open_interest": "持仓量异常",
    "trade_flow": "主动成交异常",
    "order_book": "盘口失衡",
}

FAMILY_CN = {
    "trend": "趋势跟随",
    "range_revert": "震荡反转",
    "transition_breakout": "转换突破",
    "attack": "攻击突破",
    "continuation": "趋势延续",
    "micro_momentum": "微动量",
    "funding": "资金费率",
    "open_interest": "持仓量突破",
    "trade_flow": "主动成交突破",
    "order_book": "盘口失衡",
}


def translate_reason(reason: str) -> str:
    return REASON_CN.get(reason, reason)


def translate_regime(regime: str | None) -> str:
    if not regime:
        return "未知行情"
    return REGIME_CN.get(regime, regime)


def reason_strategy_family(reason: str) -> str:
    if reason.startswith("range_revert_"):
        return "震荡反转"
    if reason.startswith("transition_breakout_"):
        return "转换突破"
    if reason.startswith("attack_"):
        return "攻击突破"
    if reason.startswith("continuation_"):
        return "趋势延续"
    if reason.startswith("micro_momentum_"):
        return "微动量"
    if reason.startswith("funding_"):
        return "资金费率"
    if reason.startswith("open_interest_"):
        return "持仓量突破"
    if reason.startswith("trade_flow_"):
        return "主动成交突破"
    if reason.startswith("order_book_"):
        return "盘口失衡"
    if reason.startswith("trend_"):
        return "趋势跟随"
    return reason


def suitable_market_for_reason(reason: str, fallback_regime: str | None = None) -> str:
    if reason.startswith("trend_long"):
        return "上涨趋势"
    if reason.startswith("trend_short"):
        return "下跌趋势"
    if reason.startswith("range_revert_") or reason.startswith("attack_exhaustion_"):
        return "震荡区间"
    if reason.startswith("transition_breakout_"):
        return "趋势转换/突破"
    if reason.startswith("continuation_"):
        return "趋势延续"
    if reason.startswith("micro_momentum_"):
        return "短线动量放大"
    if reason.startswith("funding_"):
        return "资金费率异常"
    if reason.startswith("open_interest_"):
        return "持仓量放大突破"
    if reason.startswith("trade_flow_"):
        return "主动成交放大突破"
    if reason.startswith("order_book_"):
        return "盘口深度失衡"
    if reason.startswith("attack_breakout_"):
        return "放量突破/加速段"
    return translate_regime(fallback_regime)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def adaptability_level(months_seen: int, profitable_months: int, median_pnl: float, win_rate: float) -> str:
    if months_seen >= 8 and profitable_months / months_seen >= 0.6 and median_pnl > 0 and win_rate >= 0.5:
        return "强"
    if months_seen >= 3 and profitable_months / months_seen >= 0.45 and median_pnl >= 0 and win_rate >= 0.45:
        return "中"
    return "弱"


def _dominant_regime_for_reason(month_candidates: list[dict], reason: str) -> str | None:
    regime_pnl: dict[str, float] = {}
    for candidate in month_candidates:
        result = candidate.get("result", {})
        for regime, stats in result.get("by_regime", {}).items():
            regime_pnl[regime] = regime_pnl.get(regime, 0.0) + float(stats.get("pnl", 0.0))
    if not regime_pnl:
        if reason.startswith("trend_long"):
            return "uptrend"
        if reason.startswith("trend_short"):
            return "downtrend"
        if reason.startswith("range_revert_"):
            return "range"
        if reason.startswith("transition_breakout_"):
            return "transition"
        return None
    return max(regime_pnl.items(), key=lambda item: item[1])[0]


def aggregate_reason_months(report: dict) -> list[dict]:
    by_reason: dict[str, dict] = {}
    for month in report.get("months", []):
        month_number = int(month["month"])
        candidates = month.get("candidates", [])
        month_reason_stats: dict[str, dict[str, float]] = {}
        for candidate in candidates:
            for reason, stats in candidate.get("result", {}).get("by_reason", {}).items():
                bucket = month_reason_stats.setdefault(reason, {"pnl": 0.0, "trades": 0, "wins": 0})
                bucket["pnl"] += float(stats.get("pnl", 0.0))
                bucket["trades"] += int(stats.get("trades", 0))
                bucket["wins"] += int(stats.get("wins", 0))
        for reason, stats in month_reason_stats.items():
            row = by_reason.setdefault(
                reason,
                {
                    "reason": reason,
                    "strategy_cn": translate_reason(reason),
                    "family_cn": reason_strategy_family(reason),
                    "months": [],
                    "monthly_pnls": [],
                    "trades": 0,
                    "wins": 0,
                    "pnl": 0.0,
                    "regimes": {},
                },
            )
            row["months"].append(month_number)
            row["monthly_pnls"].append(round(stats["pnl"], 4))
            row["trades"] += int(stats["trades"])
            row["wins"] += int(stats["wins"])
            row["pnl"] += float(stats["pnl"])
            regime = _dominant_regime_for_reason(candidates, reason)
            if regime:
                row["regimes"][regime] = row["regimes"].get(regime, 0) + 1

    rows: list[dict] = []
    for row in by_reason.values():
        months_seen = len(row["months"])
        profitable_months = sum(1 for value in row["monthly_pnls"] if value > 0)
        win_rate = row["wins"] / row["trades"] if row["trades"] else 0.0
        median_pnl = _median(row["monthly_pnls"])
        main_regime = max(row["regimes"].items(), key=lambda item: item[1])[0] if row["regimes"] else None
        rows.append(
            {
                "reason": row["reason"],
                "strategy_cn": row["strategy_cn"],
                "family_cn": row["family_cn"],
                "suitable_market_cn": suitable_market_for_reason(row["reason"], main_regime),
                "months_seen": months_seen,
                "profitable_months": profitable_months,
                "profit_month_ratio": round(profitable_months / months_seen, 4) if months_seen else 0.0,
                "trades": row["trades"],
                "wins": row["wins"],
                "win_rate": round(win_rate, 4),
                "pnl": round(row["pnl"], 4),
                "median_month_pnl": round(median_pnl, 4),
                "months": row["months"],
                "monthly_pnls": row["monthly_pnls"],
                "adaptability_cn": adaptability_level(months_seen, profitable_months, median_pnl, win_rate),
            }
        )
    rows.sort(
        key=lambda item: (
            {"强": 2, "中": 1, "弱": 0}[item["adaptability_cn"]],
            item["profit_month_ratio"],
            item["median_month_pnl"],
            item["pnl"],
            item["trades"],
        ),
        reverse=True,
    )
    return rows


def build_adaptation_report(report: dict) -> dict:
    rows = aggregate_reason_months(report)
    return {
        "source_months": len(report.get("months", [])),
        "strategies": rows,
        "strong": [row for row in rows if row["adaptability_cn"] == "强"],
        "medium": [row for row in rows if row["adaptability_cn"] == "中"],
        "weak": [row for row in rows if row["adaptability_cn"] == "弱"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit strategy adaptability across monthly candidate windows.")
    parser.add_argument("monthly_report", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reports/strategy_adaptation_audit.json"))
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    payload = json.loads(args.monthly_report.read_text(encoding="utf-8"))
    report = build_adaptation_report(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    for row in report["strategies"][: args.top]:
        print(
            f"{row['strategy_cn']} | 策略族={row['family_cn']} | 适合行情={row['suitable_market_cn']} | "
            f"适应性={row['adaptability_cn']} | 月份={row['profitable_months']}/{row['months_seen']} | "
            f"收益={row['pnl']:.4f} | 月中位={row['median_month_pnl']:.4f} | "
            f"胜率={row['win_rate'] * 100:.2f}% | 交易={row['trades']}"
        )


if __name__ == "__main__":
    main()
