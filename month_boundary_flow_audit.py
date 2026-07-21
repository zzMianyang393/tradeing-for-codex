"""Fixed-rule, regime-conditioned audit for the month-boundary flow proxy."""

from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from ema_crossover_4h_audit import ema_values
from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DAY_MS, parse_day, trade_event, wilder_atr
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry

FORMATION = ("2024-01-01", "2024-12-31")
OOS = ("2025-01-01", "2025-07-10")
RULE_ID = "month_boundary_flow_proxy_v1"


def split(ts: int) -> str | None:
    if parse_day(FORMATION[0]) <= ts <= parse_day(FORMATION[1], end=True): return "formation"
    if parse_day(OOS[0]) <= ts <= parse_day(OOS[1], end=True): return "oos"
    return None


def is_last_two_days(ts: int) -> bool:
    day = datetime.fromtimestamp(ts / 1000, timezone.utc).date()
    return (day.month != (day.fromordinal(day.toordinal() + 1)).month or day.month != (day.fromordinal(day.toordinal() + 2)).month)


def events(symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
    daily, labels = resample_minutes(bars, 1440), label_completed_4h_bars(bars)
    ema20, atr = ema_values(daily, 20), wilder_atr(daily, 14)
    result: list[dict[str, Any]] = []
    next_available = 0
    for i in range(20, len(daily) - 7):
        signal_ts = daily[i].ts + DAY_MS
        if signal_ts < next_available or split(signal_ts) is None or not is_last_two_days(daily[i].ts): continue
        if atr[i - 1] is None or ema20[i] is None or daily[i - 5].close <= 0: continue
        roc5 = daily[i].close / daily[i - 5].close - 1
        if daily[i].close <= ema20[i] or roc5 <= 0 or regime_at_entry(labels, signal_ts) != "趋势上行": continue
        exit_ts = None
        for j in range(i + 1, min(i + 6, len(daily))):
            if ema20[j] is not None and daily[j].close < ema20[j]:
                exit_ts = daily[j].ts + DAY_MS; break
        event = trade_event(symbol, RULE_ID, "long", signal_ts + FOUR_HOURS_MS, bars, float(atr[i - 1]), exit_ts, 5 * DAY_MS, parse_day(OOS[1], end=True), "趋势上行")
        if event:
            event["split"] = split(signal_ts); event["roc5_pct"] = round(roc5 * 100, 6); result.append(event); next_available = int(event["exit_ts"]) + 15 * 60 * 1000
    return result


def _month_concentration(items: list[dict[str, Any]]) -> float:
    """Max positive-return contribution from any single month (0.0-1.0)."""
    from collections import defaultdict
    by_month: dict[str, float] = defaultdict(float)
    total_positive = 0.0
    for e in items:
        v = float(e["net_return_pct"])
        if v > 0:
            month = datetime.fromtimestamp(e["signal_ts"] / 1000, timezone.utc).strftime("%Y-%m")
            by_month[month] += v
            total_positive += v
    if total_positive <= 0:
        return 0.0
    return max(by_month.values()) / total_positive


def summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(x["net_return_pct"]) for x in items]
    return {"events": len(items), "net_sum_pct": round(sum(values), 6), "mean_pct": round(mean(values), 6) if values else 0.0, "win_rate": round(sum(x > 0 for x in values) / len(values), 6) if values else 0.0}


def build(data: Path, symbols: list[str]) -> dict[str, Any]:
    all_events = [e for symbol in symbols for e in events(symbol, load_quantify_15m_csv(data / f"{symbol.split('-',1)[0]}_15m.csv"))]
    buckets = {name: [e for e in all_events if e["split"] == name] for name in ("formation", "oos")}
    stats = {name: summary(items) for name, items in buckets.items()}
    reasons = []
    status = "historical_research_candidate"
    for name in ("formation", "oos"):
        if stats[name]["events"] < 15:
            reasons.append(f"{name} events {stats[name]['events']} < 15")
            status = "insufficient_evidence"
        elif stats[name]["mean_pct"] <= 0:
            reasons.append(f"{name} mean <= 0")
            status = "historical_rejected"
        else:
            conc = _month_concentration(buckets[name])
            if conc > 0.25:
                reasons.append(f"{name} month concentration {conc:.1%} > 25%")
                status = "historical_rejected"
    return {"report_type": "month_boundary_flow_audit", "rule_id": RULE_ID, "parameters": {"ema": 20, "roc_days": 5, "hold_days": 5, "friction_pct": 0.16, "entry_delay_hours": 4, "atr_period": 14, "stop_atr_multiple": 2.0}, "formation": stats["formation"], "oos": stats["oos"], "events": all_events, "status": status, "reasons": reasons, "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False}}


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--data",type=Path,default=Path("data")); p.add_argument("--out",type=Path,default=Path("reports/month_boundary_flow_audit.json")); p.add_argument("--symbols",nargs="+",default=["BTC-USDT-SWAP","ETH-USDT-SWAP"]); a=p.parse_args()
    r=build(a.data,a.symbols); a.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding="utf-8"); print(f"formation={r['formation']['events']}; oos={r['oos']['events']}; status={r['status']}"); return 0

if __name__ == "__main__": raise SystemExit(main())
