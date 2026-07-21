"""Extract failed events from rejected strategy reports into a unified dataset.

This is a READ-ONLY data extraction script.  It does NOT:
- Create trading signals
- Optimize parameters
- Connect to any strategy or runner

It extracts per-event data from rejected strategy reports and outputs a
standardized JSON dataset for downstream "no-trade filter" research.

If a report has no per-event details, it is recorded as skipped_sources.
Events are NOT fabricated from aggregate statistics.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


REPORTS_DIR = Path("reports")


def load_report(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _parse_month(ts_ms: int | None, day_str: str | None) -> str:
    """Extract YYYY-MM from timestamp or day string."""
    if day_str and len(day_str) >= 7:
        return day_str[:7]
    if ts_ms:
        try:
            return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m")
        except (OSError, ValueError):
            pass
    return "unknown"


def _extract_forward_return(event: dict, horizon_key: str = "fwd_16bar") -> tuple[float | None, float | None]:
    """Extract gross and net return from an event's aggregate/fwd structure."""
    agg = event.get("aggregate", event.get("forward_returns", {}))
    if not isinstance(agg, dict):
        return None, None

    # Try the specified horizon first, then fallback
    for key in [horizon_key, "fwd_96bar", "fwd_4bar", "fwd_1bar"]:
        h = agg.get(key)
        if isinstance(h, dict):
            gross = h.get("mean_pct", h.get("ret_pct"))
            net = h.get("mean_net_pct", h.get("net_mean_pct", h.get("net_ret_pct")))
            if gross is not None and net is not None:
                return round(gross, 4), round(net, 4)
    return None, None


def _classify_failure_reason(event: dict) -> str:
    """Classify the failure reason for an event."""
    gross, net = _extract_forward_return(event)
    if net is not None and net < -0.5:
        return "severe_loss"
    if net is not None and net < 0:
        return "net_negative"
    if gross is not None and gross < 0:
        return "gross_negative"
    return "unknown"


def extract_from_range_regime_funding(report: dict, source: str) -> list[dict]:
    """Extract from range_regime_funding_extreme_audit format."""
    events = []
    overall = report.get("overall", {})
    event_list = overall.get("event_details", report.get("event_details", []))
    if not isinstance(event_list, list):
        return events

    for ev in event_list:
        fts = ev.get("funding_ts", ev.get("ts"))
        day = ev.get("day", "")
        if fts:
            day = datetime.fromtimestamp(fts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

        gross, net = _extract_forward_return(ev)

        events.append({
            "strategy_id": "range_regime_funding_extreme",
            "source_report": source,
            "event_time": day,
            "symbol": ev.get("symbol", "multi_coin"),
            "regime": ev.get("regime", "震荡"),
            "holding_hours": 4,
            "gross_return": gross,
            "net_return": net,
            "cost_bps": 14,
            "month": _parse_month(fts, day),
            "failure_reason": _classify_failure_reason(ev),
        })

    return events


def extract_from_funding_oi(report: dict, source: str) -> list[dict]:
    """Extract from funding_oi_trend_confirmation format."""
    events = []
    formation = report.get("formation", {})
    event_list = formation.get("event_details", report.get("event_details", []))
    if not isinstance(event_list, list):
        return events

    for ev in event_list:
        day = ev.get("event_day", ev.get("day", ""))
        scenario = ev.get("scenario", "unknown")

        # Get 4h return (fwd_16bar)
        gross, net = _extract_forward_return(ev)

        events.append({
            "strategy_id": "funding_oi_trend_confirmation",
            "source_report": source,
            "event_time": day,
            "symbol": "multi_coin",
            "regime": scenario,
            "holding_hours": 4,
            "gross_return": gross,
            "net_return": net,
            "cost_bps": 14,
            "month": _parse_month(None, day),
            "failure_reason": _classify_failure_reason(ev),
        })

    return events


def extract_from_multi_coin_funding(report: dict, source: str) -> list[dict]:
    """Extract from multi_coin_funding_crowding_audit format."""
    events = []
    event_list = report.get("event_details", [])
    if not isinstance(event_list, list):
        return events

    for ev in event_list:
        day = ev.get("event_day", ev.get("day", ""))
        fts = ev.get("event_ts")

        gross, net = _extract_forward_return(ev)

        events.append({
            "strategy_id": "multi_coin_funding_crowding",
            "source_report": source,
            "event_time": day,
            "symbol": "multi_coin",
            "regime": "funding_extreme",
            "holding_hours": 4,
            "gross_return": gross,
            "net_return": net,
            "cost_bps": 16,
            "month": _parse_month(fts, day),
            "failure_reason": _classify_failure_reason(ev),
        })

    return events


def extract_generic_events(report: dict, source: str, strategy_id: str) -> list[dict]:
    """Generic extraction: try event_details, formation.event_details, overall.event_details."""
    events = []

    for key_path in [
        lambda r: r.get("event_details", []),
        lambda r: r.get("formation", {}).get("event_details", []),
        lambda r: r.get("overall", {}).get("event_details", []),
    ]:
        event_list = key_path(report)
        if not isinstance(event_list, list) or not event_list:
            continue

        for ev in event_list:
            day = ev.get("event_day", ev.get("day", ""))
            fts = ev.get("event_ts", ev.get("funding_ts"))
            scenario = ev.get("scenario", "unknown")
            symbol = ev.get("symbol", "multi_coin")

            gross, net = _extract_forward_return(ev)

            events.append({
                "strategy_id": strategy_id,
                "source_report": source,
                "event_time": day,
                "symbol": symbol,
                "regime": scenario,
                "holding_hours": 4,
                "gross_return": gross,
                "net_return": net,
                "cost_bps": 14,
                "month": _parse_month(fts, day),
                "failure_reason": _classify_failure_reason(ev),
            })
        break  # only take first non-empty

    return events


# ── registry of extractors ───────────────────────────────────────────────────

EXTRACTOR_MAP: dict[str, callable] = {
    "range_regime_funding_extreme_audit": extract_from_range_regime_funding,
    "funding_oi_trend_confirmation_repaired": extract_from_funding_oi,
    "multi_coin_funding_crowding_audit": extract_from_multi_coin_funding,
}


def extract_events_from_report(report: dict, source: str, strategy_id: str) -> list[dict]:
    """Route to the appropriate extractor or use generic."""
    # Try by source name match
    for key, extractor in EXTRACTOR_MAP.items():
        if key in source:
            return extractor(report, source)

    # Fallback to generic
    return extract_generic_events(report, source, strategy_id)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Extract failed events from rejected strategy reports.")
    p.add_argument("--registry", type=Path, default=Path("reports/research_approval_registry.json"))
    p.add_argument("--out", type=Path, default=Path("reports/rejected_event_dataset.json"))
    args = p.parse_args(argv)

    # Load registry
    reg = load_report(args.registry)
    if not reg:
        print("ERROR: Cannot load registry")
        return 1

    rejected = [r for r in reg.get("records", []) if r.get("status") == "rejected"]
    print(f"Found {len(rejected)} rejected entries in registry")

    all_events: list[dict] = []
    skipped_sources: list[dict] = []
    processed_reports: list[str] = []

    for entry in rejected:
        strategy_id = entry.get("research_id", "unknown")
        evidence_paths = entry.get("evidence_paths", [])

        for ep in evidence_paths:
            path = Path(ep)
            if not path.exists():
                continue
            if path.suffix != ".json":
                continue  # skip markdown files

            report = load_report(path)
            if not report:
                skipped_sources.append({
                    "source": str(path),
                    "strategy_id": strategy_id,
                    "reason": "load_failed",
                })
                continue

            events = extract_events_from_report(report, path.name, strategy_id)
            if events:
                all_events.extend(events)
                processed_reports.append(f"{strategy_id}/{path.name}")
                print(f"  {strategy_id}/{path.name}: {len(events)} events extracted")
            else:
                skipped_sources.append({
                    "source": str(path),
                    "strategy_id": strategy_id,
                    "reason": "no_event_details",
                })

    # Deduplicate by (strategy_id, event_time, symbol)
    seen = set()
    deduped: list[dict] = []
    for ev in all_events:
        key = (ev["strategy_id"], ev["event_time"], ev["symbol"])
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    output = {
        "dataset_type": "rejected_event_extraction",
        "description": "Unified failed events from rejected strategy reports",
        "extraction_date": "2026-07-12",
        "total_events": len(deduped),
        "total_raw_events": len(all_events),
        "duplicates_removed": len(all_events) - len(deduped),
        "processed_reports": processed_reports,
        "skipped_sources": skipped_sources,
        "events": deduped,
        "methodology_notes": [
            "Events are extracted from rejected strategy reports only.",
            "Reports without per-event details are skipped (not fabricated).",
            "Cost is from the original report (14 or 16 bps round trip).",
            "Holding period is from the original report.",
            "Failure reason is classified by net return magnitude.",
            "This dataset is for research only, not for trading.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")

    print(f"\n{'='*60}")
    print(f"Total events: {len(deduped)}")
    print(f"Processed reports: {len(processed_reports)}")
    print(f"Skipped sources: {len(skipped_sources)}")
    for s in skipped_sources:
        print(f"  SKIP: {s['strategy_id']}/{s['source']} ({s['reason']})")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
