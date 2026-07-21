"""Extract read-only feature time series for combo research diagnostics.

This module is not a combo backtester. It only normalizes existing audit events
from directional feature candidates into a common event and monthly series
format. No weights are calculated and no trading entry point is imported.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


AUDIT_REPORTS = {
    "donchian_atr_trend_baseline": Path("reports/donchian_atr_trend_baseline_regime_conditioned_audit.json"),
    "daily_bb_mean_revert": Path("reports/daily_bb_mean_revert_regime_conditioned_audit.json"),
    "daily_rsi_mean_revert": Path("reports/daily_rsi_downtrend_rebound_regime_conditioned_audit.json"),
    "daily_trend_pullback": Path("reports/daily_trend_pullback_regime_conditioned_audit.json"),
    "4h_ema_crossover": Path("reports/ema_crossover_4h_regime_conditioned_audit.json"),
    "daily_parabolic_sar_trend": Path("reports/daily_parabolic_sar_trend_audit.json"),
}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def direction_sign(value: str | None) -> int:
    if value == "short":
        return -1
    return 1


def normalize_event(feature_id: str, event: dict[str, Any]) -> dict[str, Any]:
    signal_time = event.get("signal_timestamp_utc", "")
    month = signal_time[:7]
    return {
        "feature_id": f"feat_{feature_id}",
        "source_research_id": feature_id,
        "symbol": event.get("symbol", ""),
        "split": event.get("split", ""),
        "signal_ts": event.get("signal_ts"),
        "signal_timestamp_utc": signal_time,
        "month": month,
        "direction": event.get("direction", "long"),
        "direction_sign": direction_sign(event.get("direction")),
        "net_return_pct": float(event.get("net_return_pct", 0.0)),
        "gross_return_pct": float(event.get("gross_return_pct", 0.0)),
        "exit_reason": event.get("exit_reason", ""),
        "entry_regime": event.get("entry_regime", ""),
        "range_compatible_regime": bool(event.get("range_compatible_regime", False)),
        "declared_compatible_regime": bool(event.get("declared_compatible_regime", event.get("direction_compatible_regime", False))),
        "trend_compatible_regime": bool(event.get("trend_compatible_regime", False)),
        "direction_compatible_regime": bool(event.get("direction_compatible_regime", False)),
    }


def should_include_event(feature_id: str, event: dict[str, Any]) -> bool:
    if feature_id in {
        "donchian_atr_trend_baseline",
        "daily_bb_mean_revert",
        "daily_rsi_mean_revert",
        "daily_trend_pullback",
    }:
        return bool(event.get("declared_compatible_regime", False))
    if feature_id == "4h_ema_crossover":
        return bool(event.get("direction_compatible_regime", False))
    if feature_id == "daily_parabolic_sar_trend":
        return event.get("entry_regime") in {"趋势上行", "趋势下行"}
    return True


def candidate_ids(preflight: dict[str, Any]) -> list[str]:
    groups = preflight.get("groups", {})
    return [
        item["source_research_id"]
        for item in groups.get("directional_feature_candidates", [])
        if item.get("source_research_id")
    ]


def extract_feature_events(preflight: dict[str, Any], report_paths: dict[str, Path] | None = None) -> tuple[list[dict], dict]:
    paths = report_paths or AUDIT_REPORTS
    events: list[dict] = []
    diagnostics: dict[str, Any] = {}

    for research_id in candidate_ids(preflight):
        path = paths.get(research_id)
        if path is None:
            diagnostics[research_id] = {"status": "missing_report_mapping"}
            continue
        report = load_json(path)
        if not report:
            diagnostics[research_id] = {"status": "missing_report"}
            continue
        raw_events = report.get("events")
        source_field = "events"
        truncated = False
        if raw_events is None:
            raw_events = report.get("event_preview", [])
            source_field = "event_preview"
            truncated = True
        normalized = [normalize_event(research_id, item) for item in raw_events if should_include_event(research_id, item)]
        events.extend(normalized)
        diagnostics[research_id] = {
            "status": "ok",
            "source_report": str(path),
            "source_field": source_field,
            "truncated": truncated,
            "events": len(normalized),
            "raw_events": len(raw_events),
            "filter": "declared_compatible_regime_only"
            if research_id in {
                "donchian_atr_trend_baseline",
                "daily_bb_mean_revert",
                "daily_rsi_mean_revert",
                "daily_trend_pullback",
            }
            else (
                "direction_compatible_regime_only"
                if research_id == "4h_ema_crossover"
                else ("trend_regime_only" if research_id == "daily_parabolic_sar_trend" else "none")
            ),
        }

    events.sort(key=lambda item: (item["signal_ts"] or 0, item["feature_id"], item["symbol"]))
    return events, diagnostics


def monthly_series(events: list[dict]) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in events:
        feature_id = event["feature_id"]
        month = event["month"]
        if not month:
            continue
        table[feature_id][month] += event["net_return_pct"]
    return {feature: dict(sorted(months.items())) for feature, months in sorted(table.items())}


def concentration_by_feature(events: list[dict]) -> dict[str, dict[str, Any]]:
    by_feature: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_feature[event["feature_id"]].append(event)

    result: dict[str, dict[str, Any]] = {}
    for feature_id, feature_events in sorted(by_feature.items()):
        positive_by_month: dict[str, float] = defaultdict(float)
        split_counts: dict[str, int] = defaultdict(int)
        for event in feature_events:
            split_counts[event["split"]] += 1
            if event["net_return_pct"] > 0:
                positive_by_month[event["month"]] += event["net_return_pct"]
        total_positive = sum(positive_by_month.values())
        top_positive = max(positive_by_month.values()) if positive_by_month else 0.0
        result[feature_id] = {
            "events": len(feature_events),
            "split_counts": dict(sorted(split_counts.items())),
            "top_month_positive_contribution_share": round(top_positive / total_positive, 6) if total_positive > 0 else 0.0,
            "positive_by_month": {key: round(value, 6) for key, value in sorted(positive_by_month.items())},
        }
    return result


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return None
    return round(cov / denom, 6)


def monthly_correlation(series: dict[str, dict[str, float]]) -> dict[str, Any]:
    features = sorted(series)
    months = sorted({month for values in series.values() for month in values})
    matrix: dict[str, dict[str, float | None]] = {}
    for left in features:
        matrix[left] = {}
        for right in features:
            left_values = [series[left].get(month, 0.0) for month in months]
            right_values = [series[right].get(month, 0.0) for month in months]
            matrix[left][right] = 1.0 if left == right else pearson(left_values, right_values)
    return {"months": months, "matrix": matrix}


def build_report(preflight: dict[str, Any], report_paths: dict[str, Path] | None = None) -> dict[str, Any]:
    events, diagnostics = extract_feature_events(preflight, report_paths)
    series = monthly_series(events)
    return {
        "report_type": "combo_feature_timeseries",
        "report_date": "2026-07-13",
        "scope": "read_only_feature_diagnostics_not_combo_backtest",
        "events": events,
        "event_count": len(events),
        "source_diagnostics": diagnostics,
        "monthly_net_return_pct_by_feature": series,
        "monthly_correlation": monthly_correlation(series),
        "concentration_by_feature": concentration_by_feature(events),
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "This report only normalizes existing audit events.",
            "No combo weights are calculated.",
            "No strategy approval is implied.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract combo feature time series.")
    parser.add_argument("--preflight", type=Path, default=Path("reports/feature_pool_preflight_review.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/combo_feature_timeseries.json"))
    args = parser.parse_args(argv)

    preflight = load_json(args.preflight)
    if not preflight:
        print("ERROR: Cannot load feature pool preflight report")
        return 1

    report = build_report(preflight)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Events: {report['event_count']}")
    print(f"Features: {len(report['monthly_net_return_pct_by_feature'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
