"""Review combo feature coverage inside each completed-4h regime bucket.

This is a coverage diagnostic, not a combo backtest. It finds which directional
weak-signal features have enough overlapping months inside the same regime to
justify a later pre-registered combo hypothesis.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


MIN_FEATURES_PER_BUCKET = 2
MIN_BUCKET_ACTIVE_MONTHS = 6
MIN_PAIR_COMMON_MONTHS = 4


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def regime_monthly_returns(events: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    table: dict[str, dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for event in events:
        regime = str(event.get("entry_regime") or "unknown")
        feature_id = str(event.get("feature_id") or "")
        month = str(event.get("month") or "")
        if not feature_id or not month:
            continue
        table[regime][feature_id][month] += float(event.get("net_return_pct", 0.0))
    return {
        regime: {
            feature_id: {month: round(value, 6) for month, value in sorted(months.items())}
            for feature_id, months in sorted(features.items())
        }
        for regime, features in sorted(table.items())
    }


def active_months(series: dict[str, float]) -> list[str]:
    return [month for month, value in sorted(series.items()) if float(value) != 0.0]


def feature_coverage(features: dict[str, dict[str, float]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for feature_id, series in sorted(features.items()):
        months = active_months(series)
        result[feature_id] = {
            "active_months": len(months),
            "first_active_month": months[0] if months else None,
            "last_active_month": months[-1] if months else None,
            "net_sum_pct": round(sum(float(value) for value in series.values()), 6),
            "positive_months": sum(1 for value in series.values() if float(value) > 0.0),
            "negative_months": sum(1 for value in series.values() if float(value) < 0.0),
        }
    return result


def pairwise_overlap(features: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for left, right in itertools.combinations(sorted(features), 2):
        left_months = set(active_months(features[left]))
        right_months = set(active_months(features[right]))
        common = sorted(left_months & right_months)
        rows.append(
            {
                "features": [left, right],
                "common_active_months": len(common),
                "months": common,
                "meets_pair_common_month_floor": len(common) >= MIN_PAIR_COMMON_MONTHS,
            }
        )
    rows.sort(key=lambda item: (-int(item["common_active_months"]), item["features"]))
    return rows


def bucket_status(features: dict[str, dict[str, float]], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    feature_count = len(features)
    union_months = sorted({month for series in features.values() for month in active_months(series)})
    viable_pairs = [pair for pair in pairs if pair["meets_pair_common_month_floor"]]
    reasons: list[str] = []
    if feature_count < MIN_FEATURES_PER_BUCKET:
        reasons.append(f"features {feature_count} < {MIN_FEATURES_PER_BUCKET}")
    if len(union_months) < MIN_BUCKET_ACTIVE_MONTHS:
        reasons.append(f"bucket active months {len(union_months)} < {MIN_BUCKET_ACTIVE_MONTHS}")
    if not viable_pairs:
        reasons.append(f"no feature pair has common active months >= {MIN_PAIR_COMMON_MONTHS}")
    return {
        "research_status": "preflight_candidate" if not reasons else "coverage_insufficient",
        "feature_count": feature_count,
        "bucket_active_months": len(union_months),
        "active_months": union_months,
        "viable_pair_count": len(viable_pairs),
        "top_viable_pairs": viable_pairs[:5],
        "reasons": reasons,
    }


def build_report(timeseries: dict[str, Any]) -> dict[str, Any]:
    events = timeseries.get("events", [])
    buckets = regime_monthly_returns(events)
    reviews: dict[str, Any] = {}
    for regime, features in buckets.items():
        coverage = feature_coverage(features)
        pairs = pairwise_overlap(features)
        reviews[regime] = {
            "status": bucket_status(features, pairs),
            "feature_coverage": coverage,
            "pairwise_overlap": pairs,
            "monthly_net_return_pct_by_feature": features,
        }
    candidates = [
        {
            "regime": regime,
            "feature_count": review["status"]["feature_count"],
            "bucket_active_months": review["status"]["bucket_active_months"],
            "viable_pair_count": review["status"]["viable_pair_count"],
            "top_viable_pairs": review["status"]["top_viable_pairs"],
        }
        for regime, review in reviews.items()
        if review["status"]["research_status"] == "preflight_candidate"
    ]
    return {
        "report_type": "regime_bucket_combo_coverage",
        "report_date": "2026-07-13",
        "scope": "regime_bucket_coverage_not_combo_backtest",
        "bucket_thresholds": {
            "min_features_per_bucket": MIN_FEATURES_PER_BUCKET,
            "min_bucket_active_months": MIN_BUCKET_ACTIVE_MONTHS,
            "min_pair_common_months": MIN_PAIR_COMMON_MONTHS,
        },
        "source_event_count": len(events),
        "regime_count": len(reviews),
        "preflight_candidate_buckets": candidates,
        "reviews": reviews,
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "This report only checks coverage inside completed-4h regime buckets.",
            "A preflight candidate bucket is allowed only for a future research card.",
            "No weights, router, execution logic, or paper-trading approval are produced.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review regime-bucket combo coverage.")
    parser.add_argument("--timeseries", type=Path, default=Path("reports/combo_feature_timeseries.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/regime_bucket_combo_coverage.json"))
    args = parser.parse_args(argv)

    timeseries = load_json(args.timeseries)
    if not timeseries:
        print("ERROR: Cannot load combo feature time series")
        return 1

    report = build_report(timeseries)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Source events: {report['source_event_count']}")
    print(f"Candidate buckets: {len(report['preflight_candidate_buckets'])}")
    for item in report["preflight_candidate_buckets"]:
        print(
            f"  - {item['regime']}: features={item['feature_count']}, "
            f"months={item['bucket_active_months']}, viable_pairs={item['viable_pair_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
