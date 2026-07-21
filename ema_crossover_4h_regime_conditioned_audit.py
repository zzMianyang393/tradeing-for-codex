"""Regime-conditioned review for the 4h EMA crossover audit.

This module does not re-trade or optimize the strategy. It annotates existing
EMA crossover events with completed-4h regime labels and reports whether the
strategy behaves better in its declared compatible trend regimes.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

from ema_crossover_4h_audit import load_ohlcv_15m
from market import load_quantify_15m_csv
from regime_validation import label_completed_4h_bars, regime_at_entry


TREND_COMPATIBLE_REGIMES = {"趋势上行", "趋势下行"}
LONG_COMPATIBLE_REGIME = "趋势上行"
SHORT_COMPATIBLE_REGIME = "趋势下行"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def base_from_symbol(symbol: str) -> str:
    return symbol.split("-", 1)[0]


def build_regime_labels(data_dir: Path, events: list[dict[str, Any]]) -> dict[str, list[tuple[int, str]]]:
    labels: dict[str, list[tuple[int, str]]] = {}
    for symbol in sorted({event.get("symbol", "") for event in events}):
        if not symbol:
            continue
        base = base_from_symbol(symbol)
        path = data_dir / f"{base}_15m.csv"
        if path.exists():
            labels[symbol] = label_completed_4h_bars(load_quantify_15m_csv(path))
    return labels


def compatible_with_direction(event: dict[str, Any], regime: str) -> bool:
    if event.get("direction") == "long":
        return regime == LONG_COMPATIBLE_REGIME
    if event.get("direction") == "short":
        return regime == SHORT_COMPATIBLE_REGIME
    return regime in TREND_COMPATIBLE_REGIMES


def annotate_events(events: list[dict[str, Any]], labels: dict[str, list[tuple[int, str]]]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for event in events:
        symbol = event.get("symbol", "")
        entry_ts = int(event.get("entry_ts", event.get("signal_ts", 0)))
        regime = regime_at_entry(labels.get(symbol, []), entry_ts)
        item = dict(event)
        item["entry_regime"] = regime
        item["trend_compatible_regime"] = regime in TREND_COMPATIBLE_REGIMES
        item["direction_compatible_regime"] = compatible_with_direction(event, regime)
        annotated.append(item)
    return annotated


def summarize(values: list[float]) -> dict[str, float | int]:
    positives = [value for value in values if value > 0]
    negatives = [value for value in values if value <= 0]
    gross_profit = sum(positives)
    gross_loss = abs(sum(negatives))
    return {
        "observations": len(values),
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "median_pct": round(median(values), 6) if values else 0.0,
        "win_rate": round(len(positives) / len(values), 6) if values else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
        "net_sum_pct": round(sum(values), 6),
    }


def summarize_bucket(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "all": summarize([float(event.get("net_return_pct", 0.0)) for event in events]),
        "long": summarize([float(event.get("net_return_pct", 0.0)) for event in events if event.get("direction") == "long"]),
        "short": summarize([float(event.get("net_return_pct", 0.0)) for event in events if event.get("direction") == "short"]),
        "regime_counts": dict(Counter(str(event.get("entry_regime", "")) for event in events)),
    }


def conditional_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split in ("formation", "oos"):
        split_events = [event for event in events if event.get("split") == split]
        result[split] = {
            "all_events": summarize_bucket(split_events),
            "trend_compatible_regime": summarize_bucket([event for event in split_events if event["trend_compatible_regime"]]),
            "non_trend_regime": summarize_bucket([event for event in split_events if not event["trend_compatible_regime"]]),
            "direction_compatible_regime": summarize_bucket([event for event in split_events if event["direction_compatible_regime"]]),
            "direction_incompatible_regime": summarize_bucket([event for event in split_events if not event["direction_compatible_regime"]]),
        }
    return result


def verdict(summary: dict[str, Any]) -> dict[str, Any]:
    oos_trend = summary["oos"]["trend_compatible_regime"]["all"]
    oos_direction = summary["oos"]["direction_compatible_regime"]["all"]
    reasons: list[str] = []
    if int(oos_trend["observations"]) < 30:
        reasons.append(f"OOS trend-compatible events {oos_trend['observations']} < 30")
    if float(oos_trend["mean_pct"]) <= 0:
        reasons.append(f"OOS trend-compatible mean {oos_trend['mean_pct']:+.6f}% <= 0")
    if float(oos_direction["mean_pct"]) <= 0:
        reasons.append(f"OOS direction-compatible mean {oos_direction['mean_pct']:+.6f}% <= 0")
    if float(oos_trend["win_rate"]) < 0.40:
        reasons.append(f"OOS trend-compatible win rate {oos_trend['win_rate']:.2%} < 40%")
    return {
        "status": "regime_conditioned_candidate" if not reasons else "regime_conditioned_rejected",
        "eligible_as_combo_directional_feature": not reasons,
        "requires_regime_gate": True,
        "compatible_regimes": sorted(TREND_COMPATIBLE_REGIMES),
        "reasons": reasons,
    }


def build_report(audit_report: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    events = audit_report.get("events", [])
    labels = build_regime_labels(data_dir, events)
    annotated = annotate_events(events, labels)
    summary = conditional_summary(annotated)
    return {
        "report_type": "ema_crossover_4h_regime_conditioned_audit",
        "report_date": "2026-07-13",
        "source_research_id": audit_report.get("research_id", "4h_ema_crossover"),
        "scope": "regime_conditioned_research_not_strategy",
        "compatible_regimes": sorted(TREND_COMPATIBLE_REGIMES),
        "summary": summary,
        "verdict": verdict(summary),
        "events": annotated,
        "event_preview": annotated[:25],
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "Regime labels use completed 4h candles and are available only after candle close.",
            "This audit does not change EMA crossover parameters.",
            "It tests whether failures concentrate outside compatible trend regimes.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regime-conditioned 4h EMA crossover audit.")
    parser.add_argument("--audit", type=Path, default=Path("reports/ema_crossover_4h_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/ema_crossover_4h_regime_conditioned_audit.json"))
    args = parser.parse_args(argv)

    audit = load_json(args.audit)
    if not audit:
        print("ERROR: Cannot load EMA crossover audit report")
        return 1
    report = build_report(audit, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Verdict: {report['verdict']['status']}")
    for reason in report["verdict"]["reasons"]:
        print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
