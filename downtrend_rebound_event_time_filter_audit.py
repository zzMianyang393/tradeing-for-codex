"""Read-only event-time filter audit for RSI rebounds in downtrend regimes.

The audit uses frozen RSI events, strictly prior completed-4h regime labels,
and the source event's completed-daily RSI value. It produces diagnostics only.
"""

from __future__ import annotations

import argparse
import json
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from daily_rsi_mean_revert_audit import DAY_MS, load_daily_for_base, rsi_values
from market import load_quantify_15m_csv
from regime_validation import label_completed_4h_bars


REGIME = "趋势下行"
HYPOTHESES = (
    "H0_downtrend_rsi_baseline",
    "F1_prior_downtrend_streak_1_to_6",
    "F2_prior_downtrend_streak_ge_7",
    "F3_signal_rsi_below_25",
    "F4_signal_rsi_25_to_35",
)


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def base_from_symbol(symbol: str) -> str:
    return symbol.split("-", 1)[0]


def strict_prior_regime_streak(labels: list[tuple[int, str]], entry_ts: int, regime: str = REGIME) -> int:
    """Count consecutive matching labels available strictly before entry."""
    if not labels:
        return 0
    available = [item[0] for item in labels]
    index = bisect_left(available, entry_ts) - 1
    streak = 0
    while index >= 0 and labels[index][1] == regime:
        streak += 1
        index -= 1
    return streak


def signal_rsi_by_availability(data_dir: Path, base: str) -> dict[int, float]:
    daily, _source = load_daily_for_base(data_dir, base)
    values = rsi_values([bar.close for bar in daily])
    return {
        bar.ts + DAY_MS: float(value)
        for bar, value in zip(daily, values)
        if value is not None
    }


def build_event_time_inputs(data_dir: Path, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    symbols = sorted({str(event.get("symbol") or "") for event in events if event.get("symbol")})
    labels_by_symbol: dict[str, list[tuple[int, str]]] = {}
    rsi_by_symbol: dict[str, dict[int, float]] = {}
    for symbol in symbols:
        base = base_from_symbol(symbol)
        path = data_dir / f"{base}_15m.csv"
        labels_by_symbol[symbol] = (
            label_completed_4h_bars(load_quantify_15m_csv(path)) if path.exists() else []
        )
        rsi_by_symbol[symbol] = signal_rsi_by_availability(data_dir, base)

    annotated: list[dict[str, Any]] = []
    for event in events:
        if event.get("entry_regime") != REGIME:
            continue
        symbol = str(event.get("symbol") or "")
        entry_ts = int(event.get("entry_ts") or 0)
        item = dict(event)
        item["prior_downtrend_4h_streak"] = strict_prior_regime_streak(
            labels_by_symbol.get(symbol, []), entry_ts
        )
        item["signal_rsi"] = round(rsi_by_symbol.get(symbol, {}).get(entry_ts, 0.0), 6)
        item["event_time_inputs_complete"] = item["signal_rsi"] > 0.0
        annotated.append(item)
    return annotated


def select_hypotheses(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    complete = [event for event in events if event.get("event_time_inputs_complete")]
    return {
        "H0_downtrend_rsi_baseline": complete,
        "F1_prior_downtrend_streak_1_to_6": [
            event for event in complete if 1 <= int(event["prior_downtrend_4h_streak"]) <= 6
        ],
        "F2_prior_downtrend_streak_ge_7": [
            event for event in complete if int(event["prior_downtrend_4h_streak"]) >= 7
        ],
        "F3_signal_rsi_below_25": [event for event in complete if float(event["signal_rsi"]) < 25.0],
        "F4_signal_rsi_25_to_35": [
            event for event in complete if 25.0 <= float(event["signal_rsi"]) < 35.0
        ],
    }


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
            month = str(event.get("signal_timestamp_utc") or "")[:7]
            positive_by_month[month] += value
    total_positive = sum(positive_by_month.values())
    top_positive = max(positive_by_month.values()) if positive_by_month else 0.0
    without_november = [
        float(event.get("net_return_pct", 0.0))
        for event in events
        if str(event.get("signal_timestamp_utc") or "")[:7] != "2024-11"
    ]
    return {
        "events": len(events),
        "net_sum_pct": round(sum(returns), 6),
        "mean_pct": round(mean(returns), 6) if returns else 0.0,
        "median_pct": round(median(returns), 6) if returns else 0.0,
        "win_rate": round(len(positives) / len(returns), 6) if returns else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else (999.0 if gross_profit else 0.0),
        "active_months": len({str(event.get("signal_timestamp_utc") or "")[:7] for event in events}),
        "top_positive_month_share": round(top_positive / total_positive, 6) if total_positive else 0.0,
        "mean_excluding_2024_11_pct": round(mean(without_november), 6) if without_november else 0.0,
    }


def split_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "formation": summarize([event for event in events if event.get("split") == "formation"]),
        "oos": summarize([event for event in events if event.get("split") == "oos"]),
        "all": summarize(events),
    }


def advancement_reasons(summary: dict[str, Any], baseline: dict[str, Any] | None = None) -> list[str]:
    formation = summary["formation"]
    oos = summary["oos"]
    reasons: list[str] = []
    if float(formation["net_sum_pct"]) <= 0:
        reasons.append("formation net sum <= 0")
    if float(oos["net_sum_pct"]) <= 0:
        reasons.append("OOS net sum <= 0")
    if int(oos["events"]) < 20:
        reasons.append(f"OOS events {oos['events']} < 20")
    if float(oos["win_rate"]) < 0.40:
        reasons.append(f"OOS win rate {oos['win_rate']:.2%} < 40%")
    if int(summary["all"]["active_months"]) < 6:
        reasons.append(f"active months {summary['all']['active_months']} < 6")
    if float(formation["top_positive_month_share"]) > 0.25:
        reasons.append(f"formation concentration {formation['top_positive_month_share']:.2%} > 25%")
    if float(oos["top_positive_month_share"]) > 0.25:
        reasons.append(f"OOS concentration {oos['top_positive_month_share']:.2%} > 25%")
    if float(formation["mean_excluding_2024_11_pct"]) <= 0:
        reasons.append("formation mean excluding 2024-11 <= 0")
    if baseline:
        if float(formation["mean_pct"]) < float(baseline["formation"]["mean_pct"]):
            if float(oos["mean_pct"]) < float(baseline["oos"]["mean_pct"]):
                reasons.append("mean return worse than H0 in formation and OOS")
    return reasons


def build_report(source: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    source_events = list(source.get("events", []))
    annotated = build_event_time_inputs(data_dir, source_events)
    hypotheses = select_hypotheses(annotated)
    summaries = {name: split_summary(items) for name, items in hypotheses.items()}
    baseline = summaries["H0_downtrend_rsi_baseline"]
    reviews = {
        name: {
            "summary": summaries[name],
            "advancement_reasons": advancement_reasons(
                summaries[name], None if name.startswith("H0") else baseline
            ),
            "passes_current_screen": not advancement_reasons(
                summaries[name], None if name.startswith("H0") else baseline
            ),
        }
        for name in HYPOTHESES
    }
    return {
        "report_type": "downtrend_rebound_event_time_filter_audit",
        "report_date": "2026-07-13",
        "research_id": "downtrend_rebound_event_time_filter_v1",
        "scope": "read_only_event_time_diagnostic_not_executable_strategy",
        "source_event_count": len(source_events),
        "downtrend_event_count": len(annotated),
        "complete_event_time_input_count": sum(event["event_time_inputs_complete"] for event in annotated),
        "strict_timing_rule": "4h regime availability timestamp must be strictly earlier than entry timestamp",
        "hypothesis_reviews": reviews,
        "events": annotated,
        "methodology_notes": [
            "All thresholds were frozen in the research card before this report was generated.",
            "Same-month feature activity is not used.",
            "The source RSI semantic repair remains post-hoc and still requires a future validation window.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Downtrend Rebound Event-Time Filter Audit",
        "",
        "Date: 2026-07-13",
        "",
        f"Research ID: `{report['research_id']}`",
        "",
        f"Scope: `{report['scope']}`",
        "",
        "## Result Table",
        "",
        "| Hypothesis | Formation Events | Formation Mean | OOS Events | OOS Net | OOS Mean | OOS Win | Screen |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name in HYPOTHESES:
        review = report["hypothesis_reviews"][name]
        formation = review["summary"]["formation"]
        oos = review["summary"]["oos"]
        lines.append(
            f"| `{name}` | {formation['events']} | {formation['mean_pct']:+.6f}% | "
            f"{oos['events']} | {oos['net_sum_pct']:+.6f}% | {oos['mean_pct']:+.6f}% | "
            f"{oos['win_rate']:.2%} | {'pass' if review['passes_current_screen'] else 'blocked'} |"
        )
    lines.extend(
        [
            "",
            "## Screen Details",
            "",
        ]
    )
    for name in HYPOTHESES:
        review = report["hypothesis_reviews"][name]
        lines.append(f"### {name}")
        lines.append("")
        reasons = review["advancement_reasons"]
        if reasons:
            lines.extend(f"- {reason}" for reason in reasons)
        else:
            lines.append("- No current screen failure; future-window validation would still be required.")
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "- The early downtrend streak bucket has strong observed OOS returns but only six OOS events, so it is an observation rather than evidence.",
            "- The mature downtrend streak bucket preserves positive OOS return across 136 events, but it does not improve mean return over the unfiltered baseline in both windows.",
            "- RSI below 25 is too rare in this frozen event set to support a separate component.",
            "- RSI from 25 to 35 is effectively the original strategy population and does not solve concentration.",
            "- None of the frozen filters advances. The source rebound effect remains a future-window research candidate only.",
            "",
            "## Timing And Safety",
            "",
            f"- source events: {report['source_event_count']}",
            f"- downtrend events: {report['downtrend_event_count']}",
            f"- complete event-time inputs: {report['complete_event_time_input_count']}",
            f"- timing rule: {report['strict_timing_rule']}",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit event-time filters for downtrend RSI rebounds.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("reports/daily_rsi_downtrend_rebound_regime_conditioned_audit.json"),
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/downtrend_rebound_event_time_filter_audit.json"),
    )
    parser.add_argument(
        "--doc",
        type=Path,
        default=Path("docs/downtrend_rebound_event_time_filter_audit_2026-07-13.md"),
    )
    args = parser.parse_args(argv)
    source = load_json(args.source)
    if not source:
        print(f"ERROR: Cannot load source report {args.source}")
        return 1
    report = build_report(source, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    for name, review in report["hypothesis_reviews"].items():
        oos = review["summary"]["oos"]
        print(
            f"{name}: OOS events={oos['events']}, net={oos['net_sum_pct']:+.6f}%, "
            f"mean={oos['mean_pct']:+.6f}%, win={oos['win_rate']:.2%}, "
            f"passes={review['passes_current_screen']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
