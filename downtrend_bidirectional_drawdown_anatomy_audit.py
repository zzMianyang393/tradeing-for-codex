"""Drawdown anatomy for the downtrend bidirectional shared-capital combo."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from daily_rsi_mean_revert_audit import DAY_MS
from downtrend_rebound_event_time_filter_audit import load_json


def format_day(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def maximum_drawdown_episode(equity_curve: list[dict[str, Any]], initial_equity: float) -> dict[str, Any]:
    if not equity_curve:
        return {
            "peak_ts": 0,
            "trough_ts": 0,
            "peak_equity": initial_equity,
            "trough_equity": initial_equity,
            "drawdown_pct": 0.0,
            "duration_days": 0,
        }
    peak_equity = float(initial_equity)
    peak_ts = int(equity_curve[0]["ts"]) - DAY_MS
    worst = 0.0
    result_peak_ts = peak_ts
    result_peak_equity = peak_equity
    trough_ts = peak_ts
    trough_equity = peak_equity
    for point in equity_curve:
        ts = int(point["ts"])
        equity = float(point["equity"])
        if equity > peak_equity:
            peak_equity = equity
            peak_ts = ts
        drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
        if drawdown > worst:
            worst = drawdown
            result_peak_ts = peak_ts
            result_peak_equity = peak_equity
            trough_ts = ts
            trough_equity = equity
    return {
        "peak_ts": result_peak_ts,
        "peak_date": format_day(result_peak_ts),
        "trough_ts": trough_ts,
        "trough_date": format_day(trough_ts),
        "peak_equity": round(result_peak_equity, 6),
        "trough_equity": round(trough_equity, 6),
        "drawdown_pct": round(worst * 100.0, 6),
        "duration_days": max(0, (trough_ts - result_peak_ts) // DAY_MS),
    }


def daily_equity_changes(equity_curve: list[dict[str, Any]], initial_equity: float) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    previous = float(initial_equity)
    for point in equity_curve:
        equity = float(point["equity"])
        change = equity / previous - 1.0 if previous > 0 else 0.0
        changes.append(
            {
                "ts": int(point["ts"]),
                "date": format_day(int(point["ts"])),
                "equity_change_pct": round(change * 100.0, 6),
                "equity": equity,
                "active_long_positions": int(point.get("active_long_positions", 0)),
                "active_short_positions": int(point.get("active_short_positions", 0)),
                "long_exposure": float(point.get("long_exposure", 0.0)),
                "short_exposure": float(point.get("short_exposure", 0.0)),
                "net_directional_exposure": float(point.get("net_directional_exposure", 0.0)),
                "component_exposure": dict(point.get("component_exposure", {})),
            }
        )
        previous = equity
    return changes


def episode_attribution(result: dict[str, Any], episode: dict[str, Any]) -> dict[str, Any]:
    start = int(episode["peak_ts"])
    end = int(episode["trough_ts"]) + DAY_MS
    points = [point for point in result.get("equity_curve", []) if start <= int(point["ts"]) <= int(episode["trough_ts"])]
    trough_point = next(
        (point for point in result.get("equity_curve", []) if int(point["ts"]) == int(episode["trough_ts"])),
        {},
    )
    overlapping = [
        position
        for position in result.get("closed_positions", [])
        if int(position.get("entry_ts") or 0) < end and int(position.get("exit_ts") or 0) >= start
    ]
    exited = [
        position
        for position in result.get("closed_positions", [])
        if start <= int(position.get("exit_ts") or 0) < end
    ]
    component_pnl: dict[str, float] = defaultdict(float)
    direction_pnl: dict[str, float] = defaultdict(float)
    for position in exited:
        pnl = float(position.get("realized_pnl") or 0.0)
        component_pnl[str(position.get("component_id") or "unknown")] += pnl
        direction_pnl[str(position.get("direction") or "long")] += pnl
    net_exposures = [float(point.get("net_directional_exposure", 0.0)) for point in points]
    long_exposures = [float(point.get("long_exposure", 0.0)) for point in points]
    short_exposures = [float(point.get("short_exposure", 0.0)) for point in points]
    return {
        "days_observed": len(points),
        "average_long_exposure": round(mean(long_exposures), 6) if long_exposures else 0.0,
        "average_short_exposure": round(mean(short_exposures), 6) if short_exposures else 0.0,
        "average_net_directional_exposure": round(mean(net_exposures), 6) if net_exposures else 0.0,
        "net_long_days": sum(value > 0.05 for value in net_exposures),
        "net_short_days": sum(value < -0.05 for value in net_exposures),
        "approximately_neutral_days": sum(abs(value) <= 0.05 for value in net_exposures),
        "trough_active_long_positions": int(trough_point.get("active_long_positions", 0)),
        "trough_active_short_positions": int(trough_point.get("active_short_positions", 0)),
        "trough_long_exposure": float(trough_point.get("long_exposure", 0.0)),
        "trough_short_exposure": float(trough_point.get("short_exposure", 0.0)),
        "trough_net_directional_exposure": float(trough_point.get("net_directional_exposure", 0.0)),
        "trough_component_exposure": dict(trough_point.get("component_exposure", {})),
        "overlapping_position_count": len(overlapping),
        "overlapping_by_component": dict(Counter(str(item.get("component_id") or "unknown") for item in overlapping)),
        "exited_position_count": len(exited),
        "realized_pnl_by_component": {key: round(value, 6) for key, value in sorted(component_pnl.items())},
        "realized_pnl_by_direction": {key: round(value, 6) for key, value in sorted(direction_pnl.items())},
    }


def build_report(combo_report: dict[str, Any]) -> dict[str, Any]:
    oos = combo_report.get("results", {}).get("oos", {})
    initial = float(oos.get("initial_equity") or 100_000.0)
    curve = list(oos.get("equity_curve", []))
    episode = maximum_drawdown_episode(curve, initial)
    attribution = episode_attribution(oos, episode)
    worst_days = sorted(daily_equity_changes(curve, initial), key=lambda item: item["equity_change_pct"])[:5]
    return {
        "report_type": "downtrend_bidirectional_drawdown_anatomy_audit",
        "report_date": "2026-07-13",
        "research_id": "downtrend_bidirectional_drawdown_anatomy_v1",
        "scope": "read_only_drawdown_diagnostic_not_risk_overlay_test",
        "source_research_id": combo_report.get("research_id"),
        "oos_total_return_pct": float(oos.get("total_return_pct", 0.0)),
        "maximum_drawdown_episode": episode,
        "episode_attribution": attribution,
        "worst_daily_equity_changes": worst_days,
        "rejection_reason_counts": dict(Counter(str(item.get("rejection_reason") or "unknown") for item in oos.get("rejected_events", []))),
        "methodology_notes": [
            "This report diagnoses the frozen portfolio result and does not test a new risk rule.",
            "Component realized PnL includes positions exiting during the peak-to-trough interval.",
            "Daily marks cannot observe intraday drawdown between completed daily closes.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    episode = report["maximum_drawdown_episode"]
    attribution = report["episode_attribution"]
    lines = [
        "# Downtrend Bidirectional Drawdown Anatomy",
        "",
        "Date: 2026-07-13",
        "",
        "## Maximum Drawdown Episode",
        "",
        f"- peak: {episode['peak_date']}, equity {episode['peak_equity']:.6f}",
        f"- trough: {episode['trough_date']}, equity {episode['trough_equity']:.6f}",
        f"- drawdown: {episode['drawdown_pct']:.6f}%",
        f"- duration: {episode['duration_days']} days",
        "",
        "## Exposure During Episode",
        "",
        f"- average long exposure: {attribution['average_long_exposure']:.2%}",
        f"- average short exposure: {attribution['average_short_exposure']:.2%}",
        f"- average net directional exposure: {attribution['average_net_directional_exposure']:.2%}",
        f"- net-long / neutral / net-short days: {attribution['net_long_days']} / {attribution['approximately_neutral_days']} / {attribution['net_short_days']}",
        f"- trough long exposure: {attribution['trough_long_exposure']:.2%}",
        f"- trough short exposure: {attribution['trough_short_exposure']:.2%}",
        f"- trough net exposure: {attribution['trough_net_directional_exposure']:.2%}",
        "",
        "## Realized PnL During Episode",
        "",
        "| Component | Realized PnL |",
        "| --- | ---: |",
    ]
    for component, pnl in report["episode_attribution"]["realized_pnl_by_component"].items():
        lines.append(f"| `{component}` | {pnl:+.6f} |")
    lines.extend(["", "## Worst Daily Equity Changes", "", "| Date | Change | Long Exposure | Short Exposure | Net Exposure |", "| --- | ---: | ---: | ---: | ---: |"])
    for item in report["worst_daily_equity_changes"]:
        lines.append(
            f"| {item['date']} | {item['equity_change_pct']:+.6f}% | {item['long_exposure']:.2%} | "
            f"{item['short_exposure']:.2%} | {item['net_directional_exposure']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- diagnostic only; no risk overlay is tested here",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explain the maximum drawdown of the downtrend bidirectional combo.")
    parser.add_argument("--source", type=Path, default=Path("reports/downtrend_bidirectional_combo_simulation.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/downtrend_bidirectional_drawdown_anatomy_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/downtrend_bidirectional_drawdown_anatomy_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    source = load_json(args.source)
    if not source:
        print(f"ERROR: Cannot load source report {args.source}")
        return 1
    report = build_report(source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    episode = report["maximum_drawdown_episode"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"drawdown={episode['drawdown_pct']:.6f}% from {episode['peak_date']} to {episode['trough_date']}; "
        f"duration={episode['duration_days']} days"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

