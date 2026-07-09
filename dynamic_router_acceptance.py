from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from strategy_adaptation_audit import translate_reason


def _strategy_index(adaptation_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["reason"]: row for row in adaptation_report.get("strategies", [])}


def _compact_strategy(reason: str, stats: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "reason": reason,
        "strategy_cn": meta.get("strategy_cn", reason),
        "suitable_market_cn": meta.get("suitable_market_cn", ""),
        "adaptability_cn": meta.get("adaptability_cn", "未知"),
        "trades": int(stats.get("trades", 0)),
        "wins": int(stats.get("wins", 0)),
        "pnl": round(float(stats.get("pnl", 0.0)), 4),
        "win_rate": round(float(stats.get("win_rate", 0.0)), 4),
    }


def _find_prefilter_candidate(report: dict[str, Any], rank: str) -> dict[str, Any] | None:
    selected = report.get("prefilter", {}).get("selected") or []
    return next((item for item in selected if item.get("rank") == rank), None)


def evaluate_window_overfit_risk(report: dict[str, Any]) -> dict[str, Any]:
    best = report.get("best") or {}
    rank = str(best.get("rank", ""))
    candidate = _find_prefilter_candidate(report, rank)
    if not candidate:
        return {
            "risk_cn": "未知",
            "evidence_cn": ["未提供预筛选窗口结果"],
            "window_results": [],
        }

    window_results = candidate.get("window_results") or {}
    compact_windows = []
    positive_windows = 0
    negative_windows = 0
    for day_text, result in sorted(window_results.items(), key=lambda item: int(item[0])):
        pnl = float(result.get("pnl", 0.0) or 0.0)
        if pnl > 0:
            positive_windows += 1
        elif pnl < 0:
            negative_windows += 1
        compact_windows.append(
            {
                "days": int(day_text),
                "pnl": round(pnl, 4),
                "max_drawdown_pct": round(float(result.get("max_drawdown_pct", 0.0) or 0.0), 4),
                "trades": int(result.get("trades", 0) or 0),
            }
        )

    full_result = best.get("result") or {}
    full_pnl = float(full_result.get("pnl", 0.0) or 0.0)
    evidence: list[str] = []
    if positive_windows and full_pnl < 0:
        evidence.append("短窗口盈利但完整窗口亏损")
    if negative_windows:
        evidence.append("至少一个预筛选窗口亏损")
    if int(full_result.get("trades", 0) or 0) < 6:
        evidence.append("完整窗口交易样本偏少")

    if positive_windows and full_pnl < 0:
        risk = "高"
    elif negative_windows or (positive_windows and full_pnl <= 0):
        risk = "中"
    else:
        risk = "低"
        evidence.append("预筛选窗口与完整窗口方向一致")

    return {
        "risk_cn": risk,
        "evidence_cn": evidence,
        "window_results": compact_windows,
    }


def _sorted_count_rows(counts: dict[str, Any], *, limit: int = 5) -> list[tuple[str, int]]:
    return sorted(
        ((key, int(value or 0)) for key, value in counts.items()),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]


def _router_action_for_rejected_strategy(reason: str, count: int, total: int) -> str:
    share = count / total if total else 0.0
    if share >= 0.20 and reason.startswith(("trend_", "range_revert_", "transition_breakout_")):
        return "优先审计"
    if share >= 0.05:
        return "观察"
    return "暂不处理"


def summarize_router_rejections(result: dict[str, Any]) -> dict[str, Any]:
    rejections = result.get("router_rejections") or {}
    total = int(rejections.get("total", 0) or 0)
    by_rejection_reason = dict(rejections.get("by_rejection_reason") or {})
    by_signal_reason = dict(rejections.get("by_signal_reason") or {})
    by_regime = dict(rejections.get("by_regime") or {})

    top_strategies = []
    for reason, count in _sorted_count_rows(by_signal_reason):
        top_strategies.append(
            {
                "reason": reason,
                "strategy_cn": translate_reason(reason),
                "count": count,
                "share": round(count / total, 4) if total else 0.0,
                "action_cn": _router_action_for_rejected_strategy(reason, count, total),
            }
        )

    diagnosis: list[str] = []
    if total <= 0:
        diagnosis.append("没有记录到路由拒绝候选")
    elif top_strategies:
        top = top_strategies[0]
        if top["action_cn"] == "优先审计":
            diagnosis.append(f"{top['strategy_cn']}候选很多但未准入，需要拆分子行情验证是否存在可启用子集")
        else:
            diagnosis.append("路由拒绝较分散，暂时不建议因为单一策略放宽准入")

    return {
        "total": total,
        "by_rejection_reason": by_rejection_reason,
        "top_rejected_strategies": top_strategies,
        "top_rejected_regimes": [
            {"regime": regime, "count": count, "share": round(count / total, 4) if total else 0.0}
            for regime, count in _sorted_count_rows(by_regime)
        ],
        "diagnosis_cn": diagnosis,
    }


def evaluate_router_report(
    report: dict[str, Any],
    adaptation_report: dict[str, Any],
    *,
    target_end_equity: float = 210.0,
    min_trades: int = 30,
    max_drawdown_pct: float = 35.0,
) -> dict[str, Any]:
    best = report.get("best") or {}
    result = dict(best.get("result") or {})
    strategy_meta = _strategy_index(adaptation_report)
    by_reason = result.get("by_reason") or {}
    allowed_reasons = tuple(report.get("router_profile", {}).get("allowed_reasons", ()))
    strategies = [
        _compact_strategy(reason, by_reason.get(reason, {}), strategy_meta.get(reason, {}))
        for reason in allowed_reasons
    ]

    end_equity = float(result.get("end_equity", 0.0) or 0.0)
    trades = int(result.get("trades", 0) or 0)
    drawdown = float(result.get("max_drawdown_pct", 0.0) or 0.0)
    target_pass = end_equity >= target_end_equity
    overfit_risk = evaluate_window_overfit_risk(report)
    router_rejection_summary = summarize_router_rejections(result)
    risk_flags: list[str] = []

    if not target_pass:
        risk_flags.append("未达到收益目标")
    if trades < min_trades:
        risk_flags.append("交易次数不足")
    if drawdown > max_drawdown_pct:
        risk_flags.append("回撤超过上限")
    if any(item["adaptability_cn"] == "弱" for item in strategies):
        risk_flags.append("包含弱适应策略")
    if any(item["pnl"] < 0 for item in strategies):
        risk_flags.append("存在拖累策略")
    if overfit_risk["risk_cn"] == "高":
        risk_flags.append("跨窗口失效风险高")

    if target_pass and not risk_flags:
        status = "可进入模拟盘观察"
    elif any(flag in risk_flags for flag in ("包含弱适应策略", "存在拖累策略", "回撤超过上限", "跨窗口失效风险高")):
        status = "不建议实盘启用"
    else:
        status = "可继续打磨"

    return {
        "mode": report.get("router_profile", {}).get("mode", ""),
        "rank": best.get("rank", ""),
        "status_cn": status,
        "target_pass": target_pass,
        "risk_flags_cn": risk_flags,
        "result": {
            "end_equity": round(end_equity, 4),
            "pnl": round(float(result.get("pnl", 0.0) or 0.0), 4),
            "return_pct": round(float(result.get("return_pct", 0.0) or 0.0), 4),
            "max_drawdown_pct": round(drawdown, 4),
            "trades": trades,
            "win_rate": round(float(result.get("win_rate", 0.0) or 0.0), 4),
        },
        "overfit_risk": overfit_risk,
        "router_rejection_summary": router_rejection_summary,
        "strategies": strategies,
    }


def compare_router_reports(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {"best_label": "", "comparisons": []}
    best = max(items, key=lambda item: float(item["verdict"]["result"].get("end_equity", 0.0)))
    comparisons: list[dict[str, Any]] = []
    baseline = items[0]
    baseline_result = baseline["verdict"]["result"]
    for item in items[1:]:
        result = item["verdict"]["result"]
        end_delta = float(result.get("end_equity", 0.0)) - float(baseline_result.get("end_equity", 0.0))
        dd_delta = float(result.get("max_drawdown_pct", 0.0)) - float(baseline_result.get("max_drawdown_pct", 0.0))
        if end_delta == 0 and dd_delta == 0:
            judgement = "收益和回撤持平"
        elif end_delta < 0 and dd_delta > 0:
            judgement = "收益下降且回撤上升"
        elif end_delta > 0 and dd_delta <= 0:
            judgement = "收益改善且回撤未升高"
        elif end_delta > 0:
            judgement = "收益改善但回撤升高"
        else:
            judgement = "收益下降"
        comparisons.append(
            {
                "label": item["label"],
                "against": baseline["label"],
                "end_equity_delta": round(end_delta, 4),
                "drawdown_delta": round(dd_delta, 4),
                "judgement_cn": judgement,
            }
        )
    return {"best_label": best["label"], "comparisons": comparisons}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate dynamic router reports with Chinese acceptance labels.")
    parser.add_argument("--adaptation-report", type=Path, default=Path("reports/strategy_adaptation_audit_prefer_qualified.json"))
    parser.add_argument("--router-report", action="append", required=True, help="label=path")
    parser.add_argument("--target-end-equity", type=float, default=210.0)
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--max-drawdown-pct", type=float, default=35.0)
    parser.add_argument("--out", type=Path, default=Path("reports/dynamic_router_acceptance.json"))
    args = parser.parse_args()

    adaptation = _load_json(args.adaptation_report)
    items = []
    for raw in args.router_report:
        label, _, path_text = raw.partition("=")
        if not path_text:
            raise ValueError("--router-report must be label=path")
        report = _load_json(Path(path_text))
        verdict = evaluate_router_report(
            report,
            adaptation,
            target_end_equity=args.target_end_equity,
            min_trades=args.min_trades,
            max_drawdown_pct=args.max_drawdown_pct,
        )
        items.append({"label": label, "path": path_text, "verdict": verdict})

    payload = {"reports": items, "comparison": compare_router_reports(items)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    print(f"最佳路由={payload['comparison']['best_label']}")
    for item in items:
        result = item["verdict"]["result"]
        flags = ",".join(item["verdict"]["risk_flags_cn"]) or "无"
        print(
            f"{item['label']}: {item['verdict']['status_cn']} equity={result['end_equity']:.4f} "
            f"return={result['return_pct']:.2f}% dd={result['max_drawdown_pct']:.2f}% "
            f"trades={result['trades']} 风险={flags}"
        )


if __name__ == "__main__":
    main()
