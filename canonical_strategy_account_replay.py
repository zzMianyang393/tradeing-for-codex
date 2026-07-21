"""Replay frozen daily research events through one constrained account model.

This is a measurement layer only.  It consumes already-recorded daily events,
uses the project-wide 0.16% round-trip cost model in the existing simulator,
and never changes a strategy's research or trading status.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from daily_rsi_mean_revert_audit import DAY_MS, PriceBar, format_utc, parse_timestamp_ms
from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from strategy_performance_inventory import EXTRA, OVERRIDES, REPORTS, equity_sharpe, load


REGISTRY = REPORTS / "research_approval_registry.json"
OUT = REPORTS / "canonical_strategy_account_replay.json"
DOC = Path("docs/canonical_strategy_account_replay_2026-07-16.md")
CACHE = REPORTS / "canonical_daily_price_cache.json"
INITIAL_CAPITAL = 100_000.0
MAX_POSITIONS = 5
POSITION_FRACTION = 0.20
REQUIRED_EVENT_FIELDS = ("symbol", "entry_ts", "exit_ts", "entry_price", "exit_price", "direction", "split")


def report_name_for(record: dict[str, Any]) -> str | None:
    override = OVERRIDES.get(str(record.get("research_id") or ""))
    if override and (REPORTS / override).exists():
        return override
    for raw_path in record.get("evidence_paths", []):
        path = Path(str(raw_path))
        if path.parts and path.parts[0] == "reports" and path.exists():
            return path.name
    return None


def catalog() -> list[dict[str, Any]]:
    registry = load(REGISTRY) or {"records": []}
    rows = [
        {
            "strategy_id": row["research_id"],
            "name_cn": row["name_cn"],
            "status": row["status"],
            "report": report_name_for(row),
        }
        for row in registry.get("records", [])
    ]
    known = {str(row["strategy_id"]) for row in rows}
    for strategy_id, (name_cn, status, report_name) in EXTRA.items():
        if strategy_id not in known:
            rows.append({"strategy_id": strategy_id, "name_cn": name_cn, "status": status, "report": report_name})
    return sorted(rows, key=lambda row: str(row["strategy_id"]))


def daily_replayability(report: dict[str, Any] | None) -> tuple[bool, str, list[dict[str, Any]]]:
    if not isinstance(report, dict):
        return False, "missing_machine_readable_report", []
    report_type = str(report.get("report_type") or "")
    events = report.get("events")
    if not report_type.startswith("daily_"):
        return False, "not_daily_event_report", []
    if not isinstance(events, list) or not events:
        return False, "no_event_ledger", []
    missing = [field for field in REQUIRED_EVENT_FIELDS if any(not event.get(field) for event in events)]
    if missing:
        return False, f"events_missing_required_fields:{','.join(missing)}", []
    valid_splits = {str(event["split"]) for event in events}
    if not valid_splits.issubset({"formation", "oos"}):
        return False, "unsupported_or_missing_split", []
    return True, "daily_event_ledger_complete", events


def compact(result: dict[str, Any]) -> dict[str, Any]:
    curve = result.get("equity_curve", [])
    return {
        "candidate_events": result["candidate_events"],
        "accepted_positions": result["accepted_positions"],
        "capacity_rejected_events": result["capacity_rejected_events"],
        "initial_equity": result["initial_equity"],
        "final_equity": result["final_equity"],
        "total_return_pct": result["total_return_pct"],
        "max_drawdown_pct": result["max_drawdown_pct"],
        "annualized_sharpe": equity_sharpe(curve),
        "realized_win_rate": result["realized_win_rate"],
        "max_concurrent_positions": result["max_concurrent_positions"],
        "capital_turnover": result["capital_turnover"],
        "top_positive_month_share": result["top_positive_month_share"],
    }


def load_daily_price_maps(data_dir: Path, events: list[dict[str, Any]]) -> dict[str, dict[int, PriceBar]]:
    """Stream source files into daily bars so 15-minute archives do not accumulate in memory."""
    maps: dict[str, dict[int, PriceBar]] = {}
    symbols = sorted({str(event["symbol"]) for event in events})
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        native_daily = data_dir / f"{base}_1d.csv"
        source = native_daily if native_daily.exists() else next(
            (data_dir / f"{base}_{timeframe}.csv" for timeframe in ("4h", "1h", "15m") if (data_dir / f"{base}_{timeframe}.csv").exists()),
            None,
        )
        daily: dict[int, PriceBar] = {}
        if source is not None:
            with source.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        raw_ts = row.get("timestamp_ms") or row.get("timestamp") or row.get("time")
                        if raw_ts is None:
                            continue
                        ts = parse_timestamp_ms(raw_ts)
                        day_ts = ts // DAY_MS * DAY_MS
                        opening, high, low, closing = (float(row[key]) for key in ("open", "high", "low", "close"))
                        volume = float(row.get("volume") or 0.0)
                    except (KeyError, TypeError, ValueError):
                        continue
                    existing = daily.get(day_ts)
                    if existing is None:
                        daily[day_ts] = PriceBar(day_ts, format_utc(day_ts), opening, high, low, closing, volume)
                    else:
                        daily[day_ts] = PriceBar(
                            day_ts, existing.timestamp_utc, existing.open, max(existing.high, high), min(existing.low, low), closing,
                            existing.volume + volume,
                        )
        maps[symbol] = daily
    return maps


def load_cached_price_maps(events: list[dict[str, Any]], cache_path: Path = CACHE) -> dict[str, dict[int, PriceBar]]:
    cached = load(cache_path) or {}
    maps: dict[str, dict[int, PriceBar]] = {}
    for symbol in sorted({str(event["symbol"]) for event in events}):
        rows = cached.get(symbol)
        if not isinstance(rows, list):
            continue
        maps[symbol] = {
            int(row["ts"]): PriceBar(int(row["ts"]), str(row["timestamp_utc"]), float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row["volume"]))
            for row in rows
        }
    return maps


def replay(events: list[dict[str, Any]], data_dir: Path) -> dict[str, Any]:
    price_maps = load_cached_price_maps(events)
    if len(price_maps) != len({str(event["symbol"]) for event in events}):
        raise ValueError("daily price cache is incomplete for replay events")
    all_result = simulate_portfolio(
        events, price_maps, initial_capital=INITIAL_CAPITAL, max_positions=MAX_POSITIONS,
        position_fraction=POSITION_FRACTION, priority_mode="event_score_then_symbol",
    )
    by_split = {}
    for split in ("formation", "oos"):
        split_events = [event for event in events if event["split"] == split]
        maps = {symbol: price_maps[symbol] for symbol in {str(event["symbol"]) for event in split_events}}
        by_split[split] = compact(simulate_portfolio(
            split_events, maps, initial_capital=INITIAL_CAPITAL, max_positions=MAX_POSITIONS,
            position_fraction=POSITION_FRACTION, priority_mode="event_score_then_symbol",
        ))
    return {"aggregate": compact(all_result), **by_split}


def build(data_dir: Path = Path("data")) -> dict[str, Any]:
    rows = []
    for item in catalog():
        report = load(REPORTS / item["report"]) if item.get("report") else None
        replayable, reason, events = daily_replayability(report)
        row = {**item, "replayability": "replayed" if replayable else "not_replayed", "reason": reason}
        if replayable:
            row["account_performance"] = replay(events, data_dir)
        else:
            row["account_performance"] = None
        rows.append(row)
    return {
        "report_type": "canonical_strategy_account_replay",
        "methodology": {
            "scope": "frozen_daily_event_ledgers_only",
            "initial_capital": INITIAL_CAPITAL,
            "max_positions": MAX_POSITIONS,
            "position_fraction": POSITION_FRACTION,
            "round_trip_cost_pct": 0.16,
            "marking_frequency": "daily",
            "non_daily_reason": "same_frequency_price_path_not_available_in_this_daily_account_simulator",
        },
        "rows": rows,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False},
    }


def number(value: Any, suffix: str = "%") -> str:
    return f"{float(value):+.3f}{suffix}" if isinstance(value, (int, float)) else "n/a"


def render(report: dict[str, Any]) -> str:
    rows = report["rows"]
    replayed = [row for row in rows if row["replayability"] == "replayed"]
    lines = [
        "# Canonical Strategy Account Replay",
        "",
        "This measures only frozen daily event ledgers through one constrained account. It does not approve any strategy for paper or live trading.",
        "",
        "| Strategy | Status | Formation | OOS | Aggregate | Max DD | Annualized Sharpe |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in replayed:
        performance = row["account_performance"]
        aggregate = performance["aggregate"]
        lines.append(
            f"| {row['name_cn']} (`{row['strategy_id']}`) | `{row['status']}` | "
            f"{number(performance['formation']['total_return_pct'])} | {number(performance['oos']['total_return_pct'])} | "
            f"{number(aggregate['total_return_pct'])} | {number(aggregate['max_drawdown_pct'])} | "
            f"{number(aggregate['annualized_sharpe'], '')} |"
        )
    lines.extend(["", "## Not Replayed", "", "These records retain their historical status; the reason below is about measurement completeness, not a new trading decision.", "", "| Strategy | Status | Reason |", "| --- | --- | --- |"])
    for row in rows:
        if row["replayability"] != "replayed":
            lines.append(f"| {row['name_cn']} (`{row['strategy_id']}`) | `{row['status']}` | `{row['reason']}` |")
    lines.extend(["", "All safety gates remain closed: `approved_for_paper=[]`, `eligible_for_paper=false`, `safe_to_enable_trading=false`.", ""])
    return "\n".join(lines)


def main() -> int:
    report = build()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    DOC.write_text(render(report), encoding="utf-8")
    replayed = sum(row["replayability"] == "replayed" for row in report["rows"])
    print(f"replayed={replayed}; total={len(report['rows'])}; written={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
