"""Extract read-only auxiliary feature time series for combo research.

Auxiliary features include context labels and risk filters.  They are not
directional alpha signals. Risk filters are normalized as veto-only events.
This module does not build a combo model, assign weights, or approve trading.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def event_series_path(feature: dict[str, Any]) -> Path | None:
    for evidence in feature.get("evidence_paths", []):
        if evidence.get("kind") == "event_series_available":
            return Path(evidence["path"])
    return None


def extract_timestamp(event: dict[str, Any]) -> tuple[int | None, str]:
    ts = event.get("signal_ts", event.get("event_ts", event.get("entry_ts")))
    timestamp = event.get(
        "signal_timestamp_utc",
        event.get("timestamp_utc", event.get("entry_timestamp_utc", "")),
    )
    return ts, str(timestamp or "")


def extract_symbol(event: dict[str, Any]) -> str:
    symbol = event.get("symbol")
    if symbol:
        return str(symbol)
    symbols = event.get("symbols")
    if isinstance(symbols, list) and symbols:
        return "MULTI"
    return ""


def context_value(event: dict[str, Any]) -> float:
    for key in ("net_return_pct", "long_net_pct", "short_net_pct", "raw_return_pct", "qualified_fraction"):
        value = event.get(key)
        if isinstance(value, int | float):
            return float(value)
    return 1.0


def diagnostic_return(event: dict[str, Any]) -> float | None:
    for key in ("net_return_pct", "long_net_pct", "short_net_pct", "raw_return_pct"):
        value = event.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def normalize_event(feature: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    ts, timestamp = extract_timestamp(event)
    role = feature["role"]
    is_risk_filter = role == "risk_filter_candidate"
    return {
        "feature_id": feature["feature_id"],
        "source_research_id": feature["source_research_id"],
        "role": role,
        "symbol": extract_symbol(event),
        "split": event.get("split", ""),
        "event_ts": ts,
        "timestamp_utc": timestamp,
        "month": timestamp[:7],
        "veto_flag": 1 if is_risk_filter else 0,
        "value": 1.0 if is_risk_filter else context_value(event),
        "diagnostic_return_pct": diagnostic_return(event),
        "allowed_as_directional": False,
        "eligible_for_paper": False,
    }


def ready_features(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in inventory.get("features", [])
        if item.get("extractability") == "event_series_available"
        and item.get("role") in {"context_label", "risk_filter_candidate"}
    ]


def extract_aux_events(inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {}
    for feature in ready_features(inventory):
        path = event_series_path(feature)
        if path is None:
            diagnostics[feature["source_research_id"]] = {"status": "missing_event_series_path"}
            continue
        report = load_json(path)
        if not report:
            diagnostics[feature["source_research_id"]] = {"status": "missing_report", "source_report": str(path)}
            continue
        raw_events = report.get("events", [])
        if not isinstance(raw_events, list):
            raw_events = []
        normalized = [normalize_event(feature, event) for event in raw_events]
        events.extend(normalized)
        diagnostics[feature["source_research_id"]] = {
            "status": "ok",
            "source_report": str(path),
            "role": feature["role"],
            "events": len(normalized),
        }
    events.sort(key=lambda item: (item["event_ts"] or 0, item["feature_id"], item["symbol"]))
    return events, diagnostics


def monthly_event_counts(events: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    table: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for event in events:
        if event["month"]:
            table[event["feature_id"]][event["month"]] += 1
    return {feature: dict(sorted(months.items())) for feature, months in sorted(table.items())}


def monthly_value_sums(events: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in events:
        if event["month"]:
            table[event["feature_id"]][event["month"]] += float(event["value"])
    return {
        feature: {month: round(value, 6) for month, value in sorted(months.items())}
        for feature, months in sorted(table.items())
    }


def role_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        role = event["role"]
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def feature_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        feature_id = event["feature_id"]
        counts[feature_id] = counts.get(feature_id, 0) + 1
    return dict(sorted(counts.items()))


def build_report(inventory: dict[str, Any]) -> dict[str, Any]:
    events, diagnostics = extract_aux_events(inventory)
    return {
        "report_type": "combo_aux_feature_timeseries",
        "report_date": "2026-07-13",
        "scope": "read_only_auxiliary_feature_diagnostics_not_combo_backtest",
        "events": events,
        "event_count": len(events),
        "role_counts": role_counts(events),
        "feature_counts": feature_counts(events),
        "source_diagnostics": diagnostics,
        "monthly_event_counts_by_feature": monthly_event_counts(events),
        "monthly_value_sums_by_feature": monthly_value_sums(events),
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "Auxiliary features are context labels or veto-only risk filters.",
            "Risk-filter value is a veto flag, not an alpha return.",
            "No combo weights are calculated.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract combo auxiliary feature time series.")
    parser.add_argument("--inventory", type=Path, default=Path("reports/combo_context_risk_feature_inventory.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/combo_aux_feature_timeseries.json"))
    args = parser.parse_args(argv)

    inventory = load_json(args.inventory)
    if not inventory:
        print("ERROR: Cannot load auxiliary feature inventory")
        return 1

    report = build_report(inventory)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Events: {report['event_count']}")
    print(f"Features: {len(report['feature_counts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
