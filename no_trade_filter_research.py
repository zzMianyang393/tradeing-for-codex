"""No-trade filter candidate research: identify market states with highest failure rates.

This is a READ-ONLY statistical script.  It does NOT:
- Create trading signals
- Generate buy/sell recommendations
- Optimize parameters
- Connect to any strategy or runner

It only outputs filter candidates: market states where failure is most concentrated.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


REPORTS_DIR = Path("reports")


def load_report(path: Path) -> dict | None:
    """Load a JSON report, returning None on any error."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def extract_events_from_report(report: dict, source: str) -> list[dict]:
    """Extract event-level data from various report formats."""
    events: list[dict] = []

    # Format 1: event_details list with aggregate/fwd_* keys
    for section_key in ["event_details", "events"]:
        section = report.get(section_key, [])
        if isinstance(section, list):
            for ev in section:
                events.append({
                    "source": source,
                    "day": ev.get("event_day", ev.get("day", "")),
                    "scenario": ev.get("scenario", "unknown"),
                    "aggregate": ev.get("aggregate", ev.get("forward_returns", {})),
                })

    # Format 2: formation section with event_details
    formation = report.get("formation", {})
    if isinstance(formation, dict):
        for ev in formation.get("event_details", []):
            events.append({
                "source": source,
                "day": ev.get("event_day", ev.get("day", "")),
                "scenario": ev.get("scenario", "unknown"),
                "aggregate": ev.get("aggregate", ev.get("forward_returns", {})),
            })

    # Format 3: overall section with n_events but no per-event data
    # Create synthetic events from summary
    overall = report.get("overall", report.get("formation", {}))
    if isinstance(overall, dict) and not events:
        n = overall.get("n_events", 0)
        fwd = overall.get("forward_returns", overall.get("forward_returns", {}))
        if n > 0 and fwd:
            for h_key, h_val in fwd.items():
                if isinstance(h_val, dict) and h_val.get("n", 0) > 0:
                    # Create a synthetic event for each horizon
                    events.append({
                        "source": source,
                        "day": "aggregate",
                        "scenario": "aggregate",
                        "aggregate": {h_key: h_val},
                        "synthetic": True,
                    })
                    break  # only take the primary horizon

    return events


def classify_failure_mode(event: dict) -> list[str]:
    """Classify what kind of failure this event represents."""
    modes: list[str] = []
    agg = event.get("aggregate", {})

    for h_key in ["fwd_16bar", "fwd_4bar", "fwd_96bar", "fwd_1bar"]:
        h = agg.get(h_key)
        if not h or not isinstance(h, dict):
            continue

        net = h.get("mean_net_pct", h.get("net_mean_pct", 0))
        wr = h.get("win_rate", 0.5)

        if net < -0.5:
            modes.append("severe_loss")
        elif net < 0:
            modes.append("net_negative")
        elif wr < 0.45:
            modes.append("low_win_rate")

        # Check for high variance (if stdev available)
        stdev = h.get("stdev_net_pct", 0)
        if stdev > 2.0:
            modes.append("high_variance")

    # Month concentration
    day = event.get("day", "")
    if day and day != "aggregate":
        month = day[:7]
        # This will be aggregated later
        event["_month"] = month

    return list(set(modes)) if modes else ["unknown"]


def identify_filter_candidates(events: list[dict]) -> list[dict]:
    """Identify market states that are filter candidates."""
    candidates: list[dict] = []

    # 1. Month concentration analysis
    month_failures: dict[str, int] = Counter()
    month_total: dict[str, int] = Counter()
    for ev in events:
        month = ev.get("_month", ev.get("day", "")[:7])
        if not month or month == "aggregat":
            continue
        month_total[month] += 1
        modes = classify_failure_mode(ev)
        if any(m in modes for m in ["severe_loss", "net_negative"]):
            month_failures[month] += 1

    for month in sorted(month_total):
        total = month_total[month]
        fails = month_failures.get(month, 0)
        if total >= 3 and fails / total > 0.7:
            candidates.append({
                "filter_type": "month_blackout",
                "value": month,
                "reason": f"{fails}/{total} events negative in {month}",
                "severity": "high" if fails / total > 0.9 else "medium",
            })

    # 2. Scenario analysis
    scenario_failures: dict[str, int] = Counter()
    scenario_total: dict[str, int] = Counter()
    for ev in events:
        scenario = ev.get("scenario", "unknown")
        scenario_total[scenario] += 1
        modes = classify_failure_mode(ev)
        if any(m in modes for m in ["severe_loss", "net_negative"]):
            scenario_failures[scenario] += 1

    for scenario in sorted(scenario_total):
        total = scenario_total[scenario]
        fails = scenario_failures.get(scenario, 0)
        if total >= 5 and fails / total > 0.6:
            candidates.append({
                "filter_type": "scenario_blackout",
                "value": scenario,
                "reason": f"{fails}/{total} events negative in scenario '{scenario}'",
                "severity": "high" if fails / total > 0.8 else "medium",
            })

    # 3. Source analysis (which research direction fails most)
    source_failures: dict[str, int] = Counter()
    source_total: dict[str, int] = Counter()
    for ev in events:
        source = ev.get("source", "unknown")
        source_total[source] += 1
        modes = classify_failure_mode(ev)
        if any(m in modes for m in ["severe_loss", "net_negative"]):
            source_failures[source] += 1

    for source in sorted(source_total):
        total = source_total[source]
        fails = source_failures.get(source, 0)
        if total >= 3 and fails / total > 0.8:
            candidates.append({
                "filter_type": "high_cost_regime",
                "value": source,
                "reason": f"{fails}/{total} events negative from '{source}'",
                "severity": "high",
            })

    # 4. Short-holding failure pattern
    short_hold_failures = 0
    short_hold_total = 0
    for ev in events:
        agg = ev.get("aggregate", {})
        for h_key in ["fwd_1bar", "fwd_4bar"]:
            h = agg.get(h_key)
            if isinstance(h, dict) and (h.get("n", 0) > 0 or "mean_net_pct" in h or "net_mean_pct" in h):
                short_hold_total += 1
                net = h.get("mean_net_pct", h.get("net_mean_pct", 0))
                if net < -0.1:
                    short_hold_failures += 1

    if short_hold_total >= 10 and short_hold_failures / short_hold_total > 0.6:
        candidates.append({
            "filter_type": "short_hold_penalty",
            "value": "15m-1h holding",
            "reason": f"{short_hold_failures}/{short_hold_total} short-holding events negative",
            "severity": "high",
        })

    return candidates


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="No-trade filter candidate research (read-only).")
    p.add_argument("--reports", nargs="+", default=[
        "reports/donchian_atr_trend_baseline_audit.json",
        "reports/range_regime_mean_reversion_audit.json",
        "reports/utc_session_breakout_audit.json",
        "reports/range_regime_funding_extreme_audit.json",
        "reports/okx_futures_calendar_spread_mean_reversion_audit.json",
        "reports/funding_oi_trend_confirmation_repaired.json",
        "reports/btc_trend_pullback_90d_alts.json",
    ])
    p.add_argument("--out", type=Path, default=Path("reports/no_trade_filter_research.json"))
    args = p.parse_args(argv)

    all_events: list[dict] = []
    report_status: dict[str, str] = {}

    for report_path in args.reports:
        path = Path(report_path)
        report = load_report(path)
        if report is None:
            report_status[path.stem] = "not_found_or_invalid"
            continue

        events = extract_events_from_report(report, path.stem)
        if events:
            all_events.extend(events)
            report_status[path.stem] = f"{len(events)} events extracted"
        else:
            report_status[path.stem] = "0 events extracted"

    print(f"Loaded {len(all_events)} events from {len(args.reports)} reports")

    # Identify filter candidates
    candidates = identify_filter_candidates(all_events)

    # Summary statistics
    failure_modes: Counter = Counter()
    for ev in all_events:
        for mode in classify_failure_mode(ev):
            failure_modes[mode] += 1

    output = {
        "audit_type": "no_trade_filter_research",
        "description": "Read-only statistical analysis of failure patterns across rejected strategies",
        "n_events_analysed": len(all_events),
        "n_reports_processed": sum(1 for v in report_status.values() if "events" in v),
        "report_status": report_status,
        "failure_mode_distribution": dict(failure_modes),
        "filter_candidates": candidates,
        "methodology_notes": [
            "This script is READ-ONLY.  It does not create trading signals.",
            "Filter candidates are suggestions for future research avoidance.",
            "None of these filters are connected to any strategy or runner.",
            "Events are extracted from rejected strategy reports.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")

    print(f"\n{'='*60}")
    print(f"Events analysed: {len(all_events)}")
    print(f"Filter candidates: {len(candidates)}")
    for c in candidates:
        print(f"  [{c['severity']}] {c['filter_type']}: {c['value']}")
        print(f"         {c['reason']}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
