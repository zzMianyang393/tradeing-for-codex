"""Read-only diagnostic audit for the downtrend rebound combo research card.

This module consumes existing feature events and tests the pre-registered H1,
H2, and H3 diagnostic hypotheses. It does not load the trading runner, produce
orders, or claim executable signal timing.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


RSI_FEATURE = "feat_daily_rsi_mean_revert"
DONCHIAN_FEATURE = "feat_donchian_atr_trend_baseline"
EMA_FEATURE = "feat_4h_ema_crossover"
REGIME = "趋势下行"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def downtrend_events(timeseries: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in timeseries.get("events", []) if event.get("entry_regime") == REGIME]


def feature_month_returns(events: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for event in events:
        feature_id = str(event.get("feature_id") or "")
        month = str(event.get("month") or "")
        if feature_id and month:
            table[feature_id][month] += float(event.get("net_return_pct", 0.0))
    return {
        feature_id: {month: round(value, 6) for month, value in sorted(months.items())}
        for feature_id, months in sorted(table.items())
    }


def active_months(table: dict[str, dict[str, float]], feature_id: str) -> set[str]:
    return {month for month, value in table.get(feature_id, {}).items() if float(value) != 0.0}


def h3_rsi_baseline(events: list[dict[str, Any]], table: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("feature_id") == RSI_FEATURE]


def h1_donchian_veto(events: list[dict[str, Any]], table: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    donchian_months = active_months(table, DONCHIAN_FEATURE)
    return [
        event
        for event in h3_rsi_baseline(events, table)
        if str(event.get("month") or "") not in donchian_months
    ]


def h2_ema_confirmation(events: list[dict[str, Any]], table: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    ema_months = active_months(table, EMA_FEATURE)
    return [
        event
        for event in h3_rsi_baseline(events, table)
        if str(event.get("month") or "") in ema_months
    ]


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [float(event.get("net_return_pct", 0.0)) for event in events]
    positives = [value for value in returns if value > 0]
    negatives = [value for value in returns if value <= 0]
    gross_profit = sum(positives)
    gross_loss = abs(sum(negatives))
    positive_by_month: dict[str, float] = defaultdict(float)
    for event in events:
        value = float(event.get("net_return_pct", 0.0))
        if value > 0:
            positive_by_month[str(event.get("month") or "")] += value
    total_positive = sum(positive_by_month.values())
    top_positive = max(positive_by_month.values()) if positive_by_month else 0.0
    return {
        "events": len(events),
        "net_sum_pct": round(sum(returns), 6),
        "mean_pct": round(mean(returns), 6) if returns else 0.0,
        "median_pct": round(median(returns), 6) if returns else 0.0,
        "win_rate": round(len(positives) / len(returns), 6) if returns else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "active_months": len({str(event.get("month") or "") for event in events}),
        "top_positive_month_share": round(top_positive / total_positive, 6) if total_positive > 0 else 0.0,
    }


def split_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "formation": summarize([event for event in events if event.get("split") == "formation"]),
        "oos": summarize([event for event in events if event.get("split") == "oos"]),
        "all": summarize(events),
    }


def rejection_reasons(summary: dict[str, Any], baseline: dict[str, Any] | None = None) -> list[str]:
    reasons: list[str] = []
    oos = summary["oos"]
    if int(oos["events"]) == 0:
        reasons.append("OOS events = 0")
    if float(oos["net_sum_pct"]) < 0:
        reasons.append(f"OOS net sum {oos['net_sum_pct']:+.6f}% < 0")
    if float(oos["win_rate"]) < 0.40:
        reasons.append(f"OOS win rate {oos['win_rate']:.2%} < 40%")
    if int(summary["all"]["active_months"]) < 6:
        reasons.append(f"active months {summary['all']['active_months']} < 6")
    if float(summary["all"]["top_positive_month_share"]) > 0.25:
        reasons.append(f"all top positive month share {summary['all']['top_positive_month_share']:.2%} > 25%")
    if float(summary["formation"]["top_positive_month_share"]) > 0.25:
        reasons.append(f"formation top positive month share {summary['formation']['top_positive_month_share']:.2%} > 25%")
    if float(summary["oos"]["top_positive_month_share"]) > 0.25:
        reasons.append(f"OOS top positive month share {summary['oos']['top_positive_month_share']:.2%} > 25%")
    if baseline and float(summary["formation"]["net_sum_pct"]) < float(baseline["formation"]["net_sum_pct"]):
        if float(summary["oos"]["net_sum_pct"]) < float(baseline["oos"]["net_sum_pct"]):
            reasons.append("worse than H3 baseline in both formation and OOS")
    return reasons


def build_report(timeseries: dict[str, Any]) -> dict[str, Any]:
    events = downtrend_events(timeseries)
    table = feature_month_returns(events)
    hypotheses = {
        "H3_rsi_standalone_bucket_baseline": h3_rsi_baseline(events, table),
        "H1_rsi_primary_donchian_veto": h1_donchian_veto(events, table),
        "H2_rsi_primary_ema_confirmation": h2_ema_confirmation(events, table),
    }
    summaries = {name: split_summary(items) for name, items in hypotheses.items()}
    baseline = summaries["H3_rsi_standalone_bucket_baseline"]
    reviews = {
        name: {
            "summary": summary,
            "rejection_reasons": rejection_reasons(summary, None if name.startswith("H3") else baseline),
        }
        for name, summary in summaries.items()
    }
    return {
        "report_type": "downtrend_rebound_combo_hypothesis_audit",
        "report_date": "2026-07-13",
        "research_id": "combo_downtrend_rebound_rsi_context_v1",
        "scope": "read_only_diagnostic_not_executable_combo_backtest",
        "regime": REGIME,
        "source_event_count": len(timeseries.get("events", [])),
        "downtrend_event_count": len(events),
        "feature_month_returns": table,
        "hypothesis_reviews": reviews,
        "diagnostic_limitations": [
            "H1 and H2 use same-month diagnostic feature activity and are not executable entry-time rules.",
            "Any future executable audit must replace monthly diagnostics with event-time available feature states.",
            "The RSI downtrend rebound semantic repair is post-hoc and requires future-window validation.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit downtrend rebound combo hypotheses.")
    parser.add_argument("--timeseries", type=Path, default=Path("reports/combo_feature_timeseries.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/downtrend_rebound_combo_hypothesis_audit.json"))
    args = parser.parse_args(argv)

    timeseries = load_json(args.timeseries)
    if not timeseries:
        print("ERROR: Cannot load combo feature time series")
        return 1

    report = build_report(timeseries)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    for name, review in report["hypothesis_reviews"].items():
        oos = review["summary"]["oos"]
        print(
            f"{name}: OOS events={oos['events']}, net={oos['net_sum_pct']:+.6f}%, "
            f"win={oos['win_rate']:.2%}, reasons={len(review['rejection_reasons'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
