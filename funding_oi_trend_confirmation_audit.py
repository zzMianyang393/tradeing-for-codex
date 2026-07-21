"""Funding + OI trend confirmation audit — CORRECTED timing.

Timing rules (no look-ahead):
  - OI daily: timestamped 16:00 UTC, available at 16:00.
  - Funding: settlements at 00:00, 08:00, 16:00 UTC.
    At 16:00 on day D, only 00:00 and 08:00 are guaranteed available.
  - Signal computed at: 16:15 UTC on day D.
  - Entry: next 15m bar open AFTER 16:15 UTC (typically 16:30).

This is an event study, NOT a strategy.  No parameter sweep.
Threshold is fixed at 60%.  Pass/fail is final.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median


DATA_DIR = Path("data")
COST_RT = 0.0014  # 0.05% taker + 0.02% slippage, round-trip
SIGNAL_HOUR_UTC = 16
SIGNAL_MINUTE_UTC = 15
THRESHOLD = 0.60


# ── data loaders ─────────────────────────────────────────────────────────────

def load_funding_by_day(symbol: str, start_ts: int, end_ts: int) -> dict[str, list[dict]]:
    """Return {day_str: [{ts_ms, rate}, ...]} for settlements in [start_ts, end_ts]."""
    path = DATA_DIR / f"{symbol}_funding.csv"
    if not path.exists():
        return {}
    out: dict[str, list[dict]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["timestamp_ms"])
                if not (start_ts <= ts <= end_ts):
                    continue
                day = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                out.setdefault(day, []).append({"ts": ts, "rate": float(row["funding_rate"])})
            except (KeyError, TypeError, ValueError):
                continue
    return out


def load_oi(symbol: str, start_ts: int, end_ts: int) -> dict[str, dict]:
    """Return {day_str: {ts_ms, oi_usd}} for daily OI records."""
    path = DATA_DIR / f"{symbol}_open_interest_1d.csv"
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["ts"])
                if not (start_ts <= ts <= end_ts):
                    continue
                day = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                out[day] = {"ts": ts, "oi_usd": float(row["open_interest_usd"])}
            except (KeyError, TypeError, ValueError):
                continue
    return out


def load_ohlcv(symbol: str, start_ts: int, end_ts: int) -> list[dict]:
    path = DATA_DIR / f"{symbol}_15m.csv"
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                if "timestamp_ms" in row:
                    ts = int(row["timestamp_ms"])
                else:
                    ts = int(
                        datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                        .replace(tzinfo=timezone.utc).timestamp() * 1000
                    )
                if start_ts <= ts <= end_ts:
                    rows.append({"ts": ts, "open": float(row["open"]), "close": float(row["close"])})
            except (KeyError, TypeError, ValueError):
                continue
    return rows


# ── signal computation ───────────────────────────────────────────────────────

def available_funding_at_1600(day_str: str, funding_by_day: dict[str, list[dict]]) -> list[dict] | None:
    """Return funding settlements available at 16:00 UTC on `day_str`.

    At 16:00 the 16:00 settlement is happening *right now* and its published
    timestamp may lag.  Conservative: only use 00:00 and 08:00 settlements.
    Returns None if fewer than 2 records (cannot compute a reliable mean).
    """
    records = funding_by_day.get(day_str, [])
    # keep only ts < 16:00 UTC on that day
    day_start = int(datetime.strptime(day_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    cutoff = day_start + 16 * 3600 * 1000
    available = [r for r in records if r["ts"] < cutoff]
    return available if len(available) >= 2 else None


def compute_signals(
    symbols: list[str],
    all_funding: dict[str, dict[str, list[dict]]],
    all_oi: dict[str, dict[str, dict]],
    reference_days: list[str],
) -> list[dict]:
    """Compute daily both_up / both_down signals with corrected timing."""
    signals: list[dict] = []
    for i in range(1, len(reference_days)):
        today = reference_days[i]
        yesterday = reference_days[i - 1]

        both_up = 0
        both_down = 0
        total = 0
        per_coin: dict[str, str] = {}

        for sym in symbols:
            # ── funding ────────────────────────────────────────────────────
            # available at 16:00 today: today's 00:00 + 08:00 settlements
            today_f = available_funding_at_1600(today, all_funding.get(sym, {}))
            yesterday_f = available_funding_at_1600(yesterday, all_funding.get(sym, {}))
            if today_f is None or yesterday_f is None:
                continue

            funding_today = mean(r["rate"] for r in today_f)
            funding_yesterday = mean(r["rate"] for r in yesterday_f)
            funding_up = funding_today > funding_yesterday

            # ── OI ─────────────────────────────────────────────────────────
            oi_map = all_oi.get(sym, {})
            if today not in oi_map or yesterday not in oi_map:
                continue
            oi_up = oi_map[today]["oi_usd"] > oi_map[yesterday]["oi_usd"]

            total += 1
            if funding_up and oi_up:
                both_up += 1
                per_coin[sym] = "both_up"
            elif not funding_up and not oi_up:
                both_down += 1
                per_coin[sym] = "both_down"
            else:
                per_coin[sym] = "mixed"

        if total < 5:
            continue

        both_up_pct = both_up / total
        both_down_pct = both_down / total

        # signal_ts = 16:15 UTC on `today`
        today_dt = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        signal_ts = int(today_dt.timestamp() * 1000) + SIGNAL_HOUR_UTC * 3600_000 + SIGNAL_MINUTE_UTC * 60_000

        signals.append({
            "day": today,
            "signal_ts": signal_ts,
            "total_coins": total,
            "both_up_pct": both_up_pct,
            "both_down_pct": both_down_pct,
            "scenario": "both_up" if both_up_pct >= THRESHOLD else ("both_down" if both_down_pct >= THRESHOLD else "none"),
            "per_coin": per_coin,
        })

    return signals


# ── forward returns ──────────────────────────────────────────────────────────

def compute_event_returns(
    events: list[dict],
    ohlcv: dict[str, list[dict]],
    horizons: list[int] = [1, 4, 16, 96],
) -> list[dict]:
    """For each event, compute per-coin forward returns starting AFTER signal_ts."""
    all_ts = sorted(set(r["ts"] for rows in ohlcv.values() for r in rows))
    ohlcv_lookup: dict[str, dict[int, dict]] = {sym: {r["ts"]: r for r in rows} for sym, rows in ohlcv.items()}

    results: list[dict] = []
    for ev in events:
        signal_ts = ev["signal_ts"]
        # entry: next 15m bar whose ts > signal_ts
        entry_idx = next((idx for idx, ts in enumerate(all_ts) if ts > signal_ts), None)
        if entry_idx is None:
            continue

        coin_returns: dict[str, dict[str, float]] = {}  # {symbol: {fwd_Nbar: net_ret}}
        for sym in ohlcv_lookup:
            lookup = ohlcv_lookup[sym]
            entry_ts = all_ts[entry_idx]
            if entry_ts not in lookup:
                continue
            entry_price = lookup[entry_ts]["open"]
            for h in horizons:
                exit_idx = entry_idx + h
                if exit_idx >= len(all_ts):
                    continue
                exit_ts = all_ts[exit_idx]
                if exit_ts not in lookup:
                    continue
                ret = (lookup[exit_ts]["close"] / entry_price - 1.0) * 100
                coin_returns.setdefault(sym, {})[f"fwd_{h}bar"] = round(ret - COST_RT * 100, 4)

        # aggregate
        agg: dict[str, dict] = {}
        for h in horizons:
            key = f"fwd_{h}bar"
            rets = [coin_returns[s][key] for s in coin_returns if key in coin_returns[s]]
            if rets:
                agg[key] = {
                    "n_coins": len(rets),
                    "mean_net_pct": round(mean(rets), 4),
                    "median_net_pct": round(median(rets), 4),
                    "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 3),
                    "positive": sum(1 for r in rets if r > 0),
                    "negative": sum(1 for r in rets if r <= 0),
                }

        results.append({
            "event_day": ev["day"],
            "scenario": ev["scenario"],
            "both_up_pct": round(ev["both_up_pct"], 3),
            "both_down_pct": round(ev["both_down_pct"], 3),
            "per_coin_net": coin_returns,
            "aggregate": agg,
        })

    return results


# ── reporting helpers ─────────────────────────────────────────────────────────

def summarise(events_with_returns: list[dict], horizons: list[int] = [1, 4, 16, 96]) -> dict:
    """Produce aggregate summary across all events."""
    fwd: dict[str, dict] = {}
    for h in horizons:
        key = f"fwd_{h}bar"
        evs = [e for e in events_with_returns if key in e.get("aggregate", {})]
        if not evs:
            continue
        means = [e["aggregate"][key]["mean_net_pct"] for e in evs]
        win_rates = [e["aggregate"][key]["win_rate"] for e in evs]
        fwd[key] = {
            "n_events": len(evs),
            "avg_net_mean_pct": round(mean(means), 4),
            "avg_win_rate": round(mean(win_rates), 3),
            "positive_events": sum(1 for m in means if m > 0),
            "negative_events": sum(1 for m in means if m <= 0),
        }
    return fwd


def coin_contribution(events_with_returns: list[dict], key: str = "fwd_96bar") -> dict:
    """Per-coin net return contribution."""
    coin_rets: dict[str, list[float]] = {}
    for ev in events_with_returns:
        for sym, fwd in ev.get("per_coin_net", {}).items():
            if key in fwd:
                coin_rets.setdefault(sym, []).append(fwd[key])

    stats: dict[str, dict] = {}
    for sym, rets in coin_rets.items():
        stats[sym] = {
            "n_events": len(rets),
            "mean_net_pct": round(mean(rets), 4),
            "positive_events": sum(1 for r in rets if r > 0),
        }

    # max single-coin contribution to total positive
    total_positive = sum(s["mean_net_pct"] * s["n_events"] for s in stats.values() if s["mean_net_pct"] > 0)
    max_coin, max_pct = "", 0.0
    for sym, s in stats.items():
        if s["mean_net_pct"] > 0 and total_positive > 0:
            contrib = s["mean_net_pct"] * s["n_events"] / total_positive
            if contrib > max_pct:
                max_pct = contrib
                max_coin = sym

    return {"per_coin": stats, "max_coin": max_coin, "max_contribution_pct": round(max_pct, 3)}


def month_concentration(events_with_returns: list[dict]) -> dict:
    mc = Counter(e["event_day"][:7] for e in events_with_returns)
    n = len(events_with_returns)
    return {
        "distribution": dict(sorted(mc.items())),
        "max_month_pct": round(max(mc.values()) / n, 3) if n else 0,
    }


def verdict(summary: dict, mc: dict, cc: dict) -> tuple[str, list[str]]:
    """Apply pre-registered pass/fail criteria."""
    reasons: list[str] = []
    passed = True

    # 1. at least 10 events in formation
    # (checked by caller; here we check the 4h horizon)
    r4 = summary.get("fwd_16bar", {})
    if r4.get("n_events", 0) < 10:
        reasons.append(f"formation events < 10 (got {r4.get('n_events', 0)})")
        passed = False

    # 2. net mean positive
    if r4.get("avg_net_mean_pct", 0) <= 0:
        reasons.append(f"formation 4h net mean {r4.get('avg_net_mean_pct', 0):+.4f}% <= 0")
        passed = False

    # 3. win rate >= 55%
    if r4.get("avg_win_rate", 0) < 0.55:
        reasons.append(f"formation 4h win rate {r4.get('avg_win_rate', 0):.1%} < 55%")
        passed = False

    # 4. no single coin > 40% of positive contribution
    if cc.get("max_contribution_pct", 0) > 0.40:
        reasons.append(f"max coin contribution {cc['max_contribution_pct']:.1%} > 40%")
        passed = False

    # 5. no single month > 30%
    if mc.get("max_month_pct", 0) > 0.30:
        reasons.append(f"max month concentration {mc['max_month_pct']:.1%} > 30%")
        passed = False

    verdict_str = "通过形成期" if passed else "淘汰"
    return verdict_str, reasons


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Funding+OI trend confirmation audit (corrected timing).")
    p.add_argument("--symbols", nargs="+", default=[
        "BTC-USDT-SWAP", "ETH-USDT-SWAP", "AAVE-USDT-SWAP", "ADA-USDT-SWAP",
        "APT-USDT-SWAP", "ARB-USDT-SWAP", "ATOM-USDT-SWAP", "AVAX-USDT-SWAP",
        "BNB-USDT-SWAP", "CRV-USDT-SWAP", "DOGE-USDT-SWAP", "DOT-USDT-SWAP",
        "DYDX-USDT-SWAP", "FIL-USDT-SWAP", "IMX-USDT-SWAP", "INJ-USDT-SWAP",
        "LINK-USDT-SWAP", "LTC-USDT-SWAP", "NEAR-USDT-SWAP", "OP-USDT-SWAP",
        "RENDER-USDT-SWAP", "STX-USDT-SWAP", "SUI-USDT-SWAP", "TIA-USDT-SWAP",
        "TRX-USDT-SWAP", "UNI-USDT-SWAP", "XRP-USDT-SWAP",
    ])
    p.add_argument("--formation-start", default="2024-07-10")
    p.add_argument("--formation-end", default="2025-01-08")
    p.add_argument("--oos-start", default="2025-01-09")
    p.add_argument("--oos-end", default="2025-07-10")
    p.add_argument("--out", type=Path, default=Path("reports/funding_oi_trend_confirmation_repaired.json"))
    args = p.parse_args(argv)

    def ts(date_str: str) -> int:
        return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    formation_start_ts = ts(args.formation_start)
    formation_end_ts = ts(args.formation_end)
    oos_start_ts = ts(args.oos_start)
    oos_end_ts = ts(args.oos_end)

    # Load data (union of both periods)
    print("Loading data...")
    all_funding: dict[str, dict[str, list[dict]]] = {}
    all_oi: dict[str, dict[str, dict]] = {}
    for sym in args.symbols:
        f = load_funding_by_day(sym, formation_start_ts, oos_end_ts)
        o = load_oi(sym, formation_start_ts, oos_end_ts)
        if f and o:
            all_funding[sym] = f
            all_oi[sym] = o
            print(f"  {sym}: funding {len(f)}d, oi {len(o)}d")

    n_symbols = len(all_funding)
    print(f"\n{n_symbols} symbols loaded")

    # Reference days (union of all funding days)
    all_days = sorted(set().union(*(d.keys() for d in all_funding.values())))
    formation_days = [d for d in all_days if args.formation_start <= d <= args.formation_end]
    oos_days = [d for d in all_days if args.oos_start <= d <= args.oos_end]
    print(f"Formation days: {len(formation_days)}, OOS days: {len(oos_days)}")

    # Compute signals
    print("\nComputing signals (threshold=60%, timing corrected)...")
    formation_signals = compute_signals(args.symbols, all_funding, all_oi, formation_days)
    oos_signals = compute_signals(args.symbols, all_funding, all_oi, oos_days)

    # Filter to target scenario
    formation_events = [s for s in formation_signals if s["scenario"] != "none"]
    oos_events = [s for s in oos_signals if s["scenario"] != "none"]
    print(f"Formation events: {len(formation_events)}  OOS events: {len(oos_events)}")

    # Load OHLCV
    print("\nLoading OHLCV...")
    ohlcv: dict[str, list[dict]] = {}
    for sym in args.symbols:
        base = sym.split("-")[0]
        rows = load_ohlcv(base, formation_start_ts, oos_end_ts + 7 * 86400_000)
        if rows:
            ohlcv[base] = rows
    print(f"OHLCV loaded for {len(ohlcv)} symbols")

    # Compute returns
    print("\nComputing forward returns...")
    formation_returns = compute_event_returns(formation_events, ohlcv)
    oos_returns = compute_event_returns(oos_events, ohlcv)

    # Summaries
    form_summary = summarise(formation_returns)
    oos_summary = summarise(oos_returns)
    form_mc = month_concentration(formation_returns)
    oos_mc = month_concentration(oos_returns) if oos_returns else {}
    form_cc = coin_contribution(formation_returns)
    oos_cc = coin_contribution(oos_returns) if oos_returns else {}

    # Verdict
    form_verdict, form_reasons = verdict(form_summary, form_mc, form_cc)

    # OOS check (only if formation passed)
    oos_verdict = "未执行"
    oos_reasons: list[str] = []
    if form_verdict == "通过形成期":
        r4_oos = oos_summary.get("fwd_16bar", {})
        if r4_oos.get("avg_net_mean_pct", 0) <= 0:
            oos_verdict = "淘汰"
            oos_reasons.append(f"OOS 4h net mean {r4_oos.get('avg_net_mean_pct', 0):+.4f}% <= 0")
        elif r4_oos.get("avg_win_rate", 0) < 0.50:
            oos_verdict = "淘汰"
            oos_reasons.append(f"OOS 4h win rate {r4_oos.get('avg_win_rate', 0):.1%} < 50%")
        else:
            oos_verdict = "通过样本外"

    report = {
        "hypothesis": "funding+OI trend confirmation (NEW hypothesis, corrected timing)",
        "timing": "signal at 16:15 UTC; entry at next 15m bar open after 16:15",
        "cost": "0.14% round trip (project default)",
        "threshold": "60% (fixed, pre-registered)",
        "n_symbols": n_symbols,
        "formation": {
            "period": f"{args.formation_start} to {args.formation_end}",
            "n_events": len(formation_returns),
            "scenarios": dict(Counter(e["scenario"] for e in formation_returns)),
            "month_concentration": form_mc,
            "coin_contribution": form_cc,
            "forward_returns": form_summary,
            "verdict": form_verdict,
            "verdict_reasons": form_reasons,
            "event_details": [
                {
                    "day": e["event_day"],
                    "scenario": e["scenario"],
                    "aggregate": e["aggregate"],
                }
                for e in formation_returns
            ],
        },
        "out_of_sample": {
            "period": f"{args.oos_start} to {args.oos_end}",
            "n_events": len(oos_returns),
            "month_concentration": oos_mc,
            "coin_contribution": oos_cc,
            "forward_returns": oos_summary,
            "verdict": oos_verdict,
            "verdict_reasons": oos_reasons,
        },
        "final_verdict": oos_verdict if form_verdict == "通过形成期" else form_verdict,
        "methodology_notes": [
            "OI daily timestamp: 16:00 UTC.",
            "Funding used: only 00:00 + 08:00 settlements (guaranteed published before 16:00).",
            "Signal computed: 16:15 UTC.",
            "Entry: next 15m bar open after 16:15 UTC (typically 16:30).",
            "Formation and OOS are strictly non-overlapping.",
            "No parameter sweep; threshold fixed at 60%.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")

    # Print verdict
    print(f"\n{'='*60}")
    print(f"Formation: {form_verdict}")
    for r in form_reasons:
        print(f"  - {r}")
    print(f"OOS:       {oos_verdict}")
    for r in oos_reasons:
        print(f"  - {r}")
    print(f"Final:     {report['final_verdict']}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
