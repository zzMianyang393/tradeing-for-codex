"""Canonical performance inventory for registered strategy research.

This report deliberately excludes unregistered experiment snapshots.  It does
not compare additive event returns with portfolio returns as if they were the
same quantity, and only computes annualized Sharpe from a daily equity curve.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import fmean, stdev
from typing import Any


REPORTS = Path("reports")
REGISTRY = REPORTS / "research_approval_registry.json"
OUT = REPORTS / "strategy_performance_inventory.json"
DOC = Path("docs/strategy_performance_inventory_2026-07-16.md")

OVERRIDES = {
    "relative_strength_persistence": "rs_persistence_entry_timing_audit.json",
    "btc_trend_pullback": "btc_trend_pullback_regime_formation.json",
    "vol_compression_breakout": "vol_compression_breakout_entry_timing_audit.json",
    "pairs_walk_forward": "pairs_walk_forward_v1.json",
    "spot_perp_basis": "okx_basis_audit.json",
    "multi_coin_funding_crowding": "multi_coin_funding_crowding_audit.json",
    "funding_oi_time_corrected": "funding_oi_trend_confirmation_repaired.json",
    "range_regime_funding_extreme": "range_regime_funding_extreme_audit.json",
    "daily_oi_independent_change": "daily_oi_independent_change_audit.json",
    "donchian_atr_trend_baseline": "donchian_atr_trend_baseline_regime_conditioned_audit.json",
    "daily_low_turnover_momentum": "daily_low_turnover_momentum_audit.json",
    "daily_ma_alignment": "daily_ma_alignment_audit.json",
    "daily_bb_mean_revert": "daily_bb_mean_revert_regime_conditioned_audit.json",
    "daily_rsi_mean_revert": "daily_rsi_mean_revert_regime_conditioned_audit.json",
    "daily_trend_pullback": "daily_trend_pullback_regime_conditioned_audit.json",
    "4h_ema_crossover": "ema_crossover_4h_regime_conditioned_audit.json",
    "range_regime_mean_reversion_family": "range_regime_mean_reversion_audit.json",
    "utc_session_breakout_family": "utc_session_breakout_audit.json",
    "okx_futures_calendar_spread": "okx_futures_calendar_spread_mean_reversion_audit.json",
    "daily_williams_r_range_reversion": "daily_williams_r_range_reversion_audit.json",
    "daily_parabolic_sar_trend": "daily_parabolic_sar_trend_audit.json",
    "daily_atr_expansion_breakout": "daily_atr_expansion_breakout_audit.json",
    "daily_volume_confirmed_breakout": "daily_volume_confirmed_breakout_audit.json",
    "regime_component_shared_capital_combo": "regime_component_walk_forward_audit.json",
}

EXTRA = {
    "daily_kama_trend": ("日线 KAMA 趋势", "historical_rejected", "daily_kama_trend_audit.json"),
    "daily_regression_channel_trend": ("日线回归通道趋势", "historical_rejected", "daily_regression_channel_trend_audit.json"),
    "daily_rsi_percentile_range_reversion": ("日线 RSI 分位数震荡回归", "insufficient_evidence", "daily_rsi_percentile_range_reversion_audit.json"),
    "daily_bias_range_reversion": ("日线 BIAS 震荡回归", "insufficient_evidence", "daily_bias_range_reversion_audit.json"),
    "daily_zscore_range_reversion": ("日线 Z-score 震荡回归", "insufficient_evidence", "daily_zscore_range_reversion_audit.json"),
    "daily_kdj_range_reversion": ("日线 KDJ 震荡回归", "insufficient_evidence", "daily_kdj_range_reversion_audit.json"),
    "daily_spring_upthrust_range_reversion": ("日线 Spring/Upthrust 反转", "insufficient_evidence", "daily_spring_upthrust_range_reversion_audit.json"),
    "daily_bb_squeeze_high_vol_breakout": ("日线 BB 挤压高波动突破", "insufficient_evidence", "daily_bb_squeeze_high_vol_breakout_audit.json"),
    "weekly_cross_sectional_short_downtrend": ("周频横截面弱势空头（下行）", "historical_rejected", "weekly_cross_sectional_short_downtrend_audit.json"),
    "weekly_cross_sectional_momentum": ("周频横截面多空动量组合", "observed_rejected", "weekly_cross_sectional_momentum_audit.json"),
    "frozen_trend_weak_factor_sleeve": ("冻结趋势弱因子组合诊断", "historical_combo_diagnostic_rejected", "frozen_trend_sleeve_combo_diagnostic.json"),
}


def load(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def event_sharpe(events: list[dict[str, Any]], split: str) -> float | None:
    values = [float(row["net_return_pct"]) for row in events if row.get("split") == split and isinstance(row.get("net_return_pct"), (int, float))]
    return round(fmean(values) / stdev(values), 6) if len(values) >= 2 and stdev(values) > 0 else None


def equity_sharpe(equity_curve: list[dict[str, Any]]) -> float | None:
    points = [(int(row["ts"]), float(row["equity"])) for row in equity_curve if isinstance(row.get("ts"), int) and isinstance(row.get("equity"), (int, float))]
    returns = [current / previous - 1.0 for (_, previous), (_, current) in zip(points, points[1:]) if previous > 0]
    intervals = sorted(current_ts - previous_ts for (previous_ts, _), (current_ts, _) in zip(points, points[1:]) if current_ts > previous_ts)
    if len(returns) < 2 or stdev(returns) == 0 or not intervals:
        return None
    median_interval_ms = intervals[len(intervals) // 2]
    periods_per_year = 365 * 86_400_000 / median_interval_ms
    return round(fmean(returns) / stdev(returns) * math.sqrt(periods_per_year), 6)


def event_window(report: dict[str, Any], name: str) -> dict[str, Any] | None:
    stats = report.get(name)
    if not isinstance(stats, dict) or "events" not in stats:
        return None
    return {"events": stats.get("events"), "net_result_pct": stats.get("net_sum_pct"), "mean_return_pct": stats.get("mean_pct"),
            "win_rate": stats.get("win_rate"), "max_drawdown_pct": None, "sharpe": event_sharpe(report.get("events", []), name),
            "sharpe_type": "event_return_nonannualized" if event_sharpe(report.get("events", []), name) is not None else "not_available",
            "basis": "additive_event_returns_not_portfolio_equity"}


def nested_net_window(stats: dict[str, Any]) -> dict[str, Any] | None:
    net = stats.get("net")
    if not isinstance(net, dict):
        return None
    return {"events": net.get("observations"), "net_result_pct": net.get("sum_pct"), "mean_return_pct": net.get("mean_pct"),
            "win_rate": net.get("win_rate"), "max_drawdown_pct": None, "sharpe": None, "sharpe_type": "not_available",
            "basis": "event_audit_not_portfolio_equity"}


def summary_stats_window(stats: dict[str, Any], basis: str) -> dict[str, Any] | None:
    if not isinstance(stats, dict):
        return None
    observations = stats.get("observations", stats.get("n", stats.get("n_events")))
    mean_value = stats.get("mean_pct", stats.get("mean_net_pct", stats.get("avg_net_mean_pct")))
    net_sum = stats.get("net_sum_pct", stats.get("sum_pct"))
    if net_sum is None and isinstance(observations, (int, float)) and isinstance(mean_value, (int, float)):
        net_sum = observations * mean_value
    if not isinstance(observations, (int, float)) and not isinstance(net_sum, (int, float)):
        return None
    return {"events": observations, "net_result_pct": net_sum, "mean_return_pct": mean_value,
            "win_rate": stats.get("win_rate", stats.get("avg_win_rate")), "max_drawdown_pct": None,
            "sharpe": None, "sharpe_type": "not_available", "basis": basis}


def regime_summary_window(stats: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("declared_compatible_regime", "direction_compatible_regime", "trend_compatible_regime", "range_compatible_regime", "all_events"):
        bucket = stats.get(key)
        if isinstance(bucket, dict):
            result = summary_stats_window(bucket.get("all", bucket), f"event_audit_{key}")
            if result is not None:
                return result
    return summary_stats_window(stats.get("all", stats), "event_audit_summary")


def portfolio_window(stats: dict[str, Any]) -> dict[str, Any]:
    curve = stats.get("equity_curve", []) if isinstance(stats.get("equity_curve"), list) else []
    return {"events": stats.get("accepted_positions", stats.get("candidate_events")), "net_result_pct": stats.get("total_return_pct"),
            "mean_return_pct": None, "win_rate": stats.get("realized_win_rate"), "max_drawdown_pct": stats.get("max_drawdown_pct"),
            "sharpe": equity_sharpe(curve), "sharpe_type": "equity_curve_annualized" if equity_sharpe(curve) is not None else "not_available",
            "basis": "shared_capital_portfolio"}


def metrics(report: dict[str, Any]) -> dict[str, Any]:
    formation, oos = event_window(report, "formation"), event_window(report, "oos")
    if formation or oos:
        return {"formation": formation, "oos": oos, "aggregate": None}
    if isinstance(report.get("results"), dict):
        results = report["results"]
        return {"formation": portfolio_window(results["formation"]) if isinstance(results.get("formation"), dict) else None,
                "oos": portfolio_window(results["oos"]) if isinstance(results.get("oos"), dict) else None, "aggregate": None}
    if isinstance(report.get("aggregate"), dict):
        return {"formation": None, "oos": None, "aggregate": portfolio_window(report["aggregate"])}
    if isinstance(report.get("shared_capital_combo"), dict) and isinstance(report["shared_capital_combo"].get("aggregate"), dict):
        return {"formation": None, "oos": None, "aggregate": portfolio_window(report["shared_capital_combo"]["aggregate"])}
    if isinstance(report.get("summary"), dict):
        summary = report["summary"]
        formation = nested_net_window(summary.get("formation", {})) if isinstance(summary.get("formation"), dict) else None
        oos = nested_net_window(summary.get("oos", {})) if isinstance(summary.get("oos"), dict) else None
        formation = formation or regime_summary_window(summary.get("formation", {}))
        oos = oos or regime_summary_window(summary.get("oos", {}))
        if formation or oos:
            return {"formation": formation, "oos": oos, "aggregate": None}
    return {"formation": None, "oos": None, "aggregate": None}


def report_for_record(record: dict[str, Any]) -> str | None:
    override = OVERRIDES.get(record["research_id"])
    if override and (REPORTS / override).exists():
        return override
    for path in record.get("evidence_paths", []):
        candidate = Path(path)
        if candidate.parts and candidate.parts[0] == "reports" and candidate.exists():
            return candidate.name
    return None


def build() -> dict[str, Any]:
    registry = load(REGISTRY) or {"records": []}
    rows = []
    for record in registry.get("records", []):
        report_name = report_for_record(record)
        report = load(REPORTS / report_name) if report_name else None
        rows.append({"strategy_id": record["research_id"], "name_cn": record["name_cn"], "status": record["status"],
                     "eligible_for_paper": bool(record.get("eligible_for_paper", False)), "report": report_name,
                     "metrics": metrics(report) if report else {"formation": None, "oos": None, "aggregate": None},
                     "metric_availability": "available" if report else "no_machine_readable_performance_report",
                     "reason": record.get("reason", "")})
    known = {row["strategy_id"] for row in rows}
    for strategy_id, (name_cn, status, report_name) in EXTRA.items():
        if strategy_id in known:
            continue
        report = load(REPORTS / report_name)
        rows.append({"strategy_id": strategy_id, "name_cn": name_cn, "status": status, "eligible_for_paper": False,
                     "report": report_name, "metrics": metrics(report) if report else {"formation": None, "oos": None, "aggregate": None},
                     "metric_availability": "available" if report else "no_machine_readable_performance_report", "reason": "current audited strategy outside the approval registry"})
    return {"report_type": "canonical_strategy_performance_inventory", "scope": "registered_directional_strategies_plus_current_audits_excludes_unregistered_experiment_snapshots",
            "row_count": len(rows), "rows": rows, "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False}}


def cell(window: dict[str, Any] | None) -> str:
    if not window:
        return "-"
    result = window.get("net_result_pct")
    return f"{result:+.3f}%" if isinstance(result, (int, float)) else "n/a"


def render(report: dict[str, Any]) -> str:
    lines = ["# Canonical Strategy Performance Inventory", "", "Scope: registered directional strategies plus current audited rules. Historical experimental snapshots are excluded.", "",
             "`事件累计` is the sum of individual net event returns, not an account-level return. `组合收益` is a shared-capital return. Sharpe is only annualized when a daily equity curve exists; otherwise the table labels a nonannualized event-return proxy or `n/a`.", "",
             "| Strategy | Status | Formation result | OOS result | Aggregate result | Max DD | Sharpe | Basis |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in report["rows"]:
        metric = row["metrics"]; aggregate = metric["aggregate"]
        primary = aggregate or metric["oos"] or metric["formation"]
        dd = primary.get("max_drawdown_pct") if primary else None; sharpe = primary.get("sharpe") if primary else None
        dd_cell = f"{dd:.3f}%" if isinstance(dd, (int, float)) else "n/a"
        sharpe_cell = f"{sharpe:.3f}" if isinstance(sharpe, (int, float)) else "n/a"
        basis = primary.get("basis", "no PnL") if primary else "no PnL"
        lines.append(f"| {row['name_cn']} (`{row['strategy_id']}`) | `{row['status']}` | {cell(metric['formation'])} | {cell(metric['oos'])} | {cell(aggregate)} | {dd_cell} | {sharpe_cell} | {basis} |")
    lines.extend(["", "All rows remain research-only: `approved_for_paper=[]`, `eligible_for_paper=false`, `safe_to_enable_trading=false`.", ""])
    return "\n".join(lines)


def main() -> int:
    report = build(); OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    DOC.write_text(render(report), encoding="utf-8")
    print(f"rows={report['row_count']}; written={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
