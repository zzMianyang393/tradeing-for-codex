"""Parameter-free failure attribution for the rejected event-trend v1."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from statistics import median
from typing import Any

from ten_u_event_trend_contract_v1 import EventTrendConfig, EventTrendResearchWindows
from ten_u_event_trend_data_v1 import HOUR_MS, parse_utc
from ten_u_event_trend_formation_v1 import (
    HourBar,
    aggregate_four_hour,
    find_ignitions,
    load_bars,
)


HORIZONS = (4, 12, 24, 48)


def _summarize(values: list[float]) -> dict[str, Any]:
    return {
        "events": len(values),
        "positive_direction_fraction": sum(value > 0 for value in values) / len(values) if values else 0.0,
        "median_directional_return_fraction": median(values) if values else 0.0,
        "mean_directional_return_fraction": sum(values) / len(values) if values else 0.0,
    }


def ignition_direction_diagnostics(
    symbol: str,
    bars: list[HourBar],
    config: EventTrendConfig,
    start_ms: int,
    end_ms: int,
) -> list[dict[str, Any]]:
    ignitions = find_ignitions(symbol, aggregate_four_hour(bars), config, start_ms, end_ms)
    by_ts = {bar.ts: index for index, bar in enumerate(bars)}
    events: list[dict[str, Any]] = []
    for ignition in ignitions:
        index = by_ts.get(ignition.signal_ts)
        if index is None or index == 0:
            continue
        reference = bars[index - 1].close
        event: dict[str, Any] = {
            "symbol": symbol,
            "direction": ignition.direction,
            "signal_ts": ignition.signal_ts,
            "score": ignition.score,
            "directional_returns": {},
        }
        sign = 1 if ignition.direction == "long" else -1
        for horizon in HORIZONS:
            target = index + horizon - 1
            if target >= len(bars) or bars[target].ts >= end_ms:
                event["directional_returns"][str(horizon)] = None
            else:
                raw_return = bars[target].close / reference - 1
                event["directional_returns"][str(horizon)] = sign * raw_return
        events.append(event)
    return events


def build_postmortem(
    formation_report_path: Path,
    dataset_manifest_path: Path,
) -> dict[str, Any]:
    formation = json.loads(formation_report_path.read_text(encoding="utf-8"))
    if formation.get("formal_status") != "formation_fail":
        raise ValueError("postmortem is only valid for a failed Formation candidate")
    if formation.get("validation_metrics_accessed") is not False:
        raise ValueError("v1 postmortem refuses a report that accessed validation")
    manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    config = EventTrendConfig()
    windows = EventTrendResearchWindows()
    start_ms, end_ms = parse_utc(windows.formation_start), parse_utc(windows.formation_end)

    ignition_events: list[dict[str, Any]] = []
    for symbol in config.symbols:
        ignition_events.extend(
            ignition_direction_diagnostics(
                symbol,
                load_bars(Path(manifest["symbols"][symbol]["path"])),
                config,
                start_ms,
                end_ms,
            )
        )
    direction_summary: dict[str, Any] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in ignition_events:
        groups[event["symbol"]].append(event)
        groups[event["direction"]].append(event)
        groups["all"].append(event)
    for group, events in groups.items():
        direction_summary[group] = {}
        for horizon in HORIZONS:
            values = [
                event["directional_returns"][str(horizon)]
                for event in events
                if event["directional_returns"][str(horizon)] is not None
            ]
            direction_summary[group][str(horizon)] = _summarize(values)

    trades = formation["primary"]["trades_detail"]
    trade_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        trade_groups[f"symbol:{trade['symbol']}"] .append(trade)
        trade_groups[f"direction:{trade['direction']}"] .append(trade)
        trade_groups[f"exit:{trade['exit_reason']}"] .append(trade)
    trade_attribution: dict[str, Any] = {}
    for key, items in sorted(trade_groups.items()):
        trade_attribution[key] = {
            "trades": len(items),
            "wins": sum(item["net_pnl"] > 0 for item in items),
            "net_pnl": sum(item["net_pnl"] for item in items),
            "stopped_then_recovered": sum(item["stopped_then_recovered_1r"] for item in items),
        }

    return {
        "report_type": "ten_u_event_trend_v1_failure_attribution",
        "formal_status": "diagnostic_only_v1_remains_rejected",
        "strategy_id": formation["strategy_id"],
        "config_fingerprint": formation["config_fingerprint"],
        "formation_status": formation["formal_status"],
        "validation_metrics_accessed": False,
        "contaminated_case_metrics_accessed": False,
        "prospective_oos_metrics_accessed": False,
        "parameter_search_performed": False,
        "direction_persistence": direction_summary,
        "trade_attribution": trade_attribution,
        "primary_failure_reasons": formation["gate_reasons"],
        "v1_reactivation_allowed": False,
        "postmortem_use": "may motivate a separately preregistered v2 but may not tune or validate v1",
    }


def main() -> int:
    report = build_postmortem(
        Path("reports/ten_u_event_trend_formation_v1.json"),
        Path("data/event_trend_v1/hourly_dataset_manifest_v1.json"),
    )
    path = Path("reports/ten_u_event_trend_postmortem_v1.json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

