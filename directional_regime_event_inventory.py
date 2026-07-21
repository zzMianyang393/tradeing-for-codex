"""Inventory directional candidate events by completed-4h regime label.

This is a diagnostic layer. It does not approve strategies, change signals, or
calculate combo weights.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any


REGIME_REPORTS = {
    "donchian_atr_trend_baseline": Path("reports/donchian_atr_trend_baseline_regime_conditioned_audit.json"),
    "daily_bb_mean_revert": Path("reports/daily_bb_mean_revert_regime_conditioned_audit.json"),
    "daily_rsi_mean_revert": Path("reports/daily_rsi_downtrend_rebound_regime_conditioned_audit.json"),
    "daily_trend_pullback": Path("reports/daily_trend_pullback_regime_conditioned_audit.json"),
    "4h_ema_crossover": Path("reports/ema_crossover_4h_regime_conditioned_audit.json"),
}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def summarize(values: list[float]) -> dict[str, float | int]:
    positives = [value for value in values if value > 0]
    negatives = [value for value in values if value <= 0]
    gross_profit = sum(positives)
    gross_loss = abs(sum(negatives))
    return {
        "observations": len(values),
        "net_sum_pct": round(sum(values), 6),
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "median_pct": round(median(values), 6) if values else 0.0,
        "win_rate": round(len(positives) / len(values), 6) if values else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
    }


def summarize_by_regime(events: list[dict[str, Any]], split: str) -> dict[str, Any]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for event in events:
        if event.get("split") != split:
            continue
        regime = str(event.get("entry_regime", "unknown"))
        buckets[regime].append(float(event.get("net_return_pct", 0.0)))
    return {regime: summarize(values) for regime, values in sorted(buckets.items())}


def best_oos_regime(regimes: dict[str, Any]) -> dict[str, Any]:
    eligible = [
        {"regime": regime, **stats}
        for regime, stats in regimes.items()
        if int(stats.get("observations", 0)) >= 10
    ]
    if not eligible:
        return {"status": "no_regime_with_min_10_oos_events"}
    best = max(eligible, key=lambda item: (float(item["mean_pct"]), float(item["net_sum_pct"])))
    return {
        "status": "ok",
        "regime": best["regime"],
        "observations": best["observations"],
        "net_sum_pct": best["net_sum_pct"],
        "mean_pct": best["mean_pct"],
        "win_rate": best["win_rate"],
    }


def build_report(report_paths: dict[str, Path] | None = None) -> dict[str, Any]:
    paths = report_paths or REGIME_REPORTS
    reviews: dict[str, Any] = {}
    for research_id, path in sorted(paths.items()):
        report = load_json(path)
        if not report:
            reviews[research_id] = {"status": "missing_report", "source_report": str(path)}
            continue
        events = report.get("events", [])
        formation = summarize_by_regime(events, "formation")
        oos = summarize_by_regime(events, "oos")
        reviews[research_id] = {
            "status": "ok",
            "source_report": str(path),
            "raw_events": len(events),
            "formation_by_regime": formation,
            "oos_by_regime": oos,
            "best_oos_regime_min_10_events": best_oos_regime(oos),
            "declared_verdict": report.get("verdict", {}),
        }
    return {
        "report_type": "directional_regime_event_inventory",
        "report_date": "2026-07-13",
        "scope": "read_only_regime_distribution_not_strategy",
        "reviews": reviews,
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "This inventory reads existing regime-conditioned event reports.",
            "It does not reclassify strategies or approve any feature.",
            "Best OOS regime is descriptive only and requires a separate pre-registered profile before reuse.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory directional events by regime.")
    parser.add_argument("--out", type=Path, default=Path("reports/directional_regime_event_inventory.json"))
    args = parser.parse_args(argv)
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    for research_id, review in report["reviews"].items():
        best = review.get("best_oos_regime_min_10_events", {})
        print(f"{research_id}: {best}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
