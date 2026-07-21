"""Regime-conditioned audits for directional weak-signal candidates.

This module annotates existing event-audit reports with completed-4h regime
labels. It does not re-run, optimize, or approve any strategy.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any

from market import load_quantify_15m_csv
from regime_validation import label_completed_4h_bars, regime_at_entry


TREND_COMPATIBLE_REGIMES = {"趋势上行", "趋势下行"}
RANGE_COMPATIBLE_REGIMES = {"震荡"}
LONG_COMPATIBLE_REGIME = "趋势上行"
SHORT_COMPATIBLE_REGIME = "趋势下行"


PROFILE_CONFIGS: dict[str, dict[str, Any]] = {
    "donchian_trend": {
        "report_type": "donchian_atr_trend_baseline_regime_conditioned_audit",
        "source_research_id": "donchian_atr_trend_baseline",
        "compatible_regimes": TREND_COMPATIBLE_REGIMES,
        "compatibility_mode": "trend_direction",
        "description": "Trend-following component: long only in uptrend, short only in downtrend.",
    },
    "daily_bb_range": {
        "report_type": "daily_bb_mean_revert_regime_conditioned_audit",
        "source_research_id": "daily_bb_mean_revert",
        "compatible_regimes": RANGE_COMPATIBLE_REGIMES,
        "compatibility_mode": "range_only",
        "description": "Mean-reversion component: long-only rebound candidate inside range regimes.",
    },
    "daily_rsi_range": {
        "report_type": "daily_rsi_mean_revert_regime_conditioned_audit",
        "source_research_id": "daily_rsi_mean_revert",
        "compatible_regimes": RANGE_COMPATIBLE_REGIMES,
        "compatibility_mode": "range_only",
        "description": "RSI mean-reversion component: long-only rebound candidate inside range regimes.",
    },
    "daily_rsi_downtrend_rebound": {
        "report_type": "daily_rsi_downtrend_rebound_regime_conditioned_audit",
        "source_research_id": "daily_rsi_mean_revert",
        "compatible_regimes": {"趋势下行"},
        "compatibility_mode": "listed_regimes",
        "description": "RSI oversold rebound component: long-only rebound candidate inside downtrend regimes.",
    },
    "daily_trend_pullback": {
        "report_type": "daily_trend_pullback_regime_conditioned_audit",
        "source_research_id": "daily_trend_pullback",
        "compatible_regimes": {"趋势上行"},
        "compatibility_mode": "trend_direction",
        "description": "Trend-pullback component: long-only entries are compatible only with uptrend regimes.",
    },
}


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
    for symbol in sorted({str(event.get("symbol", "")) for event in events}):
        if not symbol:
            continue
        path = data_dir / f"{base_from_symbol(symbol)}_15m.csv"
        if path.exists():
            labels[symbol] = label_completed_4h_bars(load_quantify_15m_csv(path))
    return labels


def is_trend_direction_compatible(event: dict[str, Any], regime: str) -> bool:
    direction = event.get("direction", "long")
    if direction == "long":
        return regime == LONG_COMPATIBLE_REGIME
    if direction == "short":
        return regime == SHORT_COMPATIBLE_REGIME
    return regime in TREND_COMPATIBLE_REGIMES


def is_declared_compatible(event: dict[str, Any], regime: str, profile: str) -> bool:
    mode = PROFILE_CONFIGS[profile]["compatibility_mode"]
    if mode == "trend_direction":
        return is_trend_direction_compatible(event, regime)
    if mode == "range_only":
        return regime in RANGE_COMPATIBLE_REGIMES
    if mode == "listed_regimes":
        return regime in PROFILE_CONFIGS[profile]["compatible_regimes"]
    return False


def annotate_events(
    events: list[dict[str, Any]],
    labels: dict[str, list[tuple[int, str]]],
    profile: str,
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for event in events:
        symbol = str(event.get("symbol", ""))
        entry_ts = int(event.get("entry_ts", event.get("signal_ts", 0)))
        regime = regime_at_entry(labels.get(symbol, []), entry_ts)
        item = dict(event)
        item["entry_regime"] = regime
        item["trend_compatible_regime"] = regime in TREND_COMPATIBLE_REGIMES
        item["range_compatible_regime"] = regime in RANGE_COMPATIBLE_REGIMES
        item["direction_compatible_regime"] = is_trend_direction_compatible(event, regime)
        item["declared_compatible_regime"] = is_declared_compatible(event, regime, profile)
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
        "long": summarize([float(event.get("net_return_pct", 0.0)) for event in events if event.get("direction", "long") == "long"]),
        "short": summarize([float(event.get("net_return_pct", 0.0)) for event in events if event.get("direction") == "short"]),
        "regime_counts": dict(Counter(str(event.get("entry_regime", "")) for event in events)),
    }


def conditional_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split in ("formation", "oos"):
        split_events = [event for event in events if event.get("split") == split]
        result[split] = {
            "all_events": summarize_bucket(split_events),
            "declared_compatible_regime": summarize_bucket([event for event in split_events if event["declared_compatible_regime"]]),
            "declared_incompatible_regime": summarize_bucket([event for event in split_events if not event["declared_compatible_regime"]]),
            "trend_compatible_regime": summarize_bucket([event for event in split_events if event["trend_compatible_regime"]]),
            "range_compatible_regime": summarize_bucket([event for event in split_events if event["range_compatible_regime"]]),
        }
    return result


def verdict(summary: dict[str, Any]) -> dict[str, Any]:
    formation = summary["formation"]["declared_compatible_regime"]["all"]
    oos = summary["oos"]["declared_compatible_regime"]["all"]
    reasons: list[str] = []
    warnings: list[str] = []
    if int(formation["observations"]) < 15:
        reasons.append(f"formation declared-compatible events {formation['observations']} < 15")
    if int(oos["observations"]) < 15:
        reasons.append(f"OOS declared-compatible events {oos['observations']} < 15")
    if float(formation["mean_pct"]) <= 0:
        warnings.append(f"formation declared-compatible mean {formation['mean_pct']:+.6f}% <= 0")
    if float(oos["mean_pct"]) <= 0:
        reasons.append(f"OOS declared-compatible mean {oos['mean_pct']:+.6f}% <= 0")
    if float(oos["win_rate"]) < 0.40:
        reasons.append(f"OOS declared-compatible win rate {oos['win_rate']:.2%} < 40%")
    return {
        "status": "regime_conditioned_candidate" if not reasons else "regime_conditioned_rejected",
        "eligible_as_combo_directional_feature": not reasons,
        "requires_regime_gate": True,
        "reasons": reasons,
        "warnings": warnings,
    }


def build_report(audit_report: dict[str, Any], data_dir: Path, profile: str) -> dict[str, Any]:
    config = PROFILE_CONFIGS[profile]
    events = audit_report.get("events", [])
    labels = build_regime_labels(data_dir, events)
    annotated = annotate_events(events, labels, profile)
    summary = conditional_summary(annotated)
    return {
        "report_type": config["report_type"],
        "report_date": "2026-07-13",
        "source_research_id": audit_report.get("research_id", config["source_research_id"]),
        "profile": profile,
        "scope": "regime_conditioned_research_not_strategy",
        "compatible_regimes": sorted(config["compatible_regimes"]),
        "compatibility_mode": config["compatibility_mode"],
        "description": config["description"],
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
            "This audit reuses frozen event reports and does not change underlying signal parameters.",
            "Declared-compatible events are the only events eligible for later combo feature extraction.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regime-conditioned audit for directional weak-signal candidates.")
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--profile", choices=sorted(PROFILE_CONFIGS), required=True)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    audit = load_json(args.audit)
    if not audit:
        print(f"ERROR: Cannot load audit report {args.audit}")
        return 1
    report = build_report(audit, args.data, args.profile)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Verdict: {report['verdict']['status']}")
    for reason in report["verdict"]["reasons"]:
        print(f"  - {reason}")
    for warning in report["verdict"]["warnings"]:
        print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
