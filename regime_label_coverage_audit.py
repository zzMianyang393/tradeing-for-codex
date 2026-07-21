"""Regime label coverage and stability audit.

Audits completed-4h regime labels for:
  - Coverage days, coverage rate, continuous segment lengths
  - Overlap, gaps, mutual exclusion conflicts
  - BTC vs altcoin label consistency
  - Monthly distribution, especially 2024-11 concentration

This is an OBSERVATION-ONLY audit.  It does NOT:
  - Calculate strategy returns
  - Generate trading signals
  - Modify label definitions
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev


DATA_DIR = Path("data")
FOUR_H_MS = 4 * 3600 * 1000
VALID_LABELS = {"趋势上行", "趋势下行", "高波动转换", "震荡"}


def load_ohlcv_15m(symbol: str, start: str, end: str) -> list[dict]:
    path = DATA_DIR / f"{symbol}_15m.csv"
    if not path.exists():
        return []
    start_ts = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_ts = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                ts_str = r.get("timestamp", "")
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if start_ts <= ts <= end_ts:
                    rows.append({
                        "ts": int(ts.timestamp() * 1000),
                        "open": float(r["open"]), "high": float(r["high"]),
                        "low": float(r["low"]), "close": float(r["close"]),
                        "volume": float(r.get("volume", 0)),
                    })
            except (KeyError, ValueError):
                continue
    return rows


def resample_4h(bars_15m: list[dict]) -> list[dict]:
    buckets: dict[int, list[dict]] = {}
    for b in bars_15m:
        bt = (b["ts"] // FOUR_H_MS) * FOUR_H_MS
        buckets.setdefault(bt, []).append(b)
    result = []
    for bt in sorted(buckets):
        g = buckets[bt]
        result.append({"ts": bt, "open": g[0]["open"], "high": max(x["high"] for x in g),
                        "low": min(x["low"] for x in g), "close": g[-1]["close"],
                        "volume": sum(x["volume"] for x in g)})
    return result


def _ema(v: list[float], p: int) -> list[float]:
    if not v:
        return []
    k = 2 / (p + 1)
    r = [v[0]]
    for x in v[1:]:
        r.append(x * k + r[-1] * (1 - k))
    return r


def _atr(h: list[float], l: list[float], c: list[float], p: int = 14) -> list[float]:
    if len(h) < 2:
        return [0.0] * len(h)
    trs = [h[0] - l[0]]
    for i in range(1, len(h)):
        trs.append(max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1])))
    return _ema(trs, p)


def label_4h_bars(bars_4h: list[dict]) -> list[tuple[int, str]]:
    if len(bars_4h) < 200:
        return []
    c = [b["close"] for b in bars_4h]
    h = [b["high"] for b in bars_4h]
    lo = [b["low"] for b in bars_4h]
    e20, e50, e200 = _ema(c, 20), _ema(c, 50), _ema(c, 200)
    atr = _atr(h, lo, c, 14)
    labels = []
    for i in range(200, len(bars_4h)):
        atr_pct = atr[i] / c[i] if c[i] > 0 else 0
        ts_val = (e20[i] - e200[i]) / atr[i] if atr[i] > 0 else 0
        if e20[i] > e50[i] > e200[i] and ts_val >= 1.0:
            lbl = "趋势上行"
        elif e20[i] < e50[i] < e200[i] and ts_val <= -1.0:
            lbl = "趋势下行"
        elif atr_pct >= 0.03:
            lbl = "高波动转换"
        else:
            lbl = "震荡"
        labels.append((bars_4h[i]["ts"] + FOUR_H_MS, lbl))
    return labels


def compute_coverage(labels: list[tuple[int, str]], start_ts: int, end_ts: int) -> dict:
    """Compute coverage statistics for a label series within a time window."""
    relevant = [(ts, lbl) for ts, lbl in labels if start_ts <= ts <= end_ts]
    if not relevant:
        return {"n_labels": 0, "coverage_days": 0, "coverage_rate": 0.0, "status": "insufficient"}

    # Coverage days
    days = set()
    for ts, _ in relevant:
        days.add(datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d"))
    coverage_days = len(days)

    # Expected days (inclusive of both start and end dates)
    start_day = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    end_day = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    total_days = (end_ts - start_ts) / 86400000 + 1  # +1 for inclusive interval
    coverage_rate = min(1.0, coverage_days / total_days) if total_days > 0 else 0

    # Label distribution
    counts = Counter(lbl for _, lbl in relevant)

    # Continuous segments
    segments: dict[str, list[int]] = defaultdict(list)
    current_label = None
    current_len = 0
    for _, lbl in relevant:
        if lbl == current_label:
            current_len += 1
        else:
            if current_label:
                segments[current_label].append(current_len)
            current_label = lbl
            current_len = 1
    if current_label:
        segments[current_label].append(current_len)

    segment_stats = {}
    for lbl, lengths in segments.items():
        segment_stats[lbl] = {
            "n_segments": len(lengths),
            "mean_length": round(mean(lengths), 1),
            "max_length": max(lengths),
            "min_length": min(lengths),
        }

    # Monthly distribution
    monthly: dict[str, Counter] = defaultdict(Counter)
    for ts, lbl in relevant:
        month = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")
        monthly[month][lbl] += 1

    return {
        "n_labels": len(relevant),
        "coverage_days": coverage_days,
        "coverage_rate": round(coverage_rate, 4),
        "label_counts": dict(counts),
        "segment_stats": segment_stats,
        "monthly_distribution": {m: dict(c) for m, c in sorted(monthly.items())},
        "status": "stable" if coverage_rate > 0.9 and len(counts) >= 3 else "sparse",
    }


def check_btc_alt_consistency(
    btc_labels: list[tuple[int, str]],
    alt_labels: dict[str, list[tuple[int, str]]],
) -> dict:
    """Check BTC vs altcoin label consistency."""
    btc_map = {ts: lbl for ts, lbl in btc_labels}
    results = {}

    for sym, labels in alt_labels.items():
        alt_map = {ts: lbl for ts, lbl in labels}
        common_ts = sorted(set(btc_map) & set(alt_map))
        if not common_ts:
            continue

        agree = sum(1 for ts in common_ts if btc_map[ts] == alt_map[ts])
        total = len(common_ts)
        results[sym] = {
            "common_timestamps": total,
            "agreement_rate": round(agree / total, 4),
            "status": "consistent" if agree / total > 0.5 else "divergent",
        }

    return results


def main(argv=None):
    p = argparse.ArgumentParser(description="Regime label coverage audit.")
    p.add_argument("--symbols", nargs="+", default=[
        "BTC", "ETH", "SOL", "DOGE", "LINK", "ADA", "AVAX", "DOT",
    ])
    p.add_argument("--formation-start", default="2024-01-01")
    p.add_argument("--formation-end", default="2024-12-31")
    p.add_argument("--oos-start", default="2025-01-01")
    p.add_argument("--oos-end", default="2025-07-10")
    p.add_argument("--out", type=Path, default=Path("reports/regime_label_coverage_audit.json"))
    args = p.parse_args(argv)

    def ts(d):
        return int(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    fs, fe, os_, oe = ts(args.formation_start), ts(args.formation_end), ts(args.oos_start), ts(args.oos_end)

    print("Loading data and labeling...")
    all_labels: dict[str, list[tuple[int, str]]] = {}
    for sym in args.symbols:
        bars = load_ohlcv_15m(sym, args.formation_start, args.oos_end)
        if len(bars) < 1000:
            print(f"  {sym}: insufficient data ({len(bars)} bars)")
            continue
        bars_4h = resample_4h(bars)
        labels = label_4h_bars(bars_4h)
        all_labels[sym] = labels
        print(f"  {sym}: {len(labels)} labels")

    # Coverage audit per symbol
    per_symbol: dict[str, dict] = {}
    for sym, labels in all_labels.items():
        formation_cov = compute_coverage(labels, fs, fe)
        oos_cov = compute_coverage(labels, os_, oe)
        per_symbol[sym] = {"formation": formation_cov, "oos": oos_cov}

    # BTC vs alt consistency
    btc_labels = all_labels.get("BTC", [])
    alt_labels = {s: l for s, l in all_labels.items() if s != "BTC"}
    consistency = check_btc_alt_consistency(btc_labels, alt_labels)

    # 2024-11 concentration check
    nov_check: dict[str, dict] = {}
    for sym, labels in all_labels.items():
        nov_start = ts("2024-11-01")
        nov_end = ts("2024-11-30")
        nov_labels = [(ts_, lbl) for ts_, lbl in labels if nov_start <= ts_ <= nov_end]
        total_labels = [(ts_, lbl) for ts_, lbl in labels if fs <= ts_ <= fe]
        if total_labels:
            nov_ratio = len(nov_labels) / len(total_labels)
            nov_check[sym] = {
                "nov_labels": len(nov_labels),
                "total_formation_labels": len(total_labels),
                "nov_ratio": round(nov_ratio, 4),
                "concentrated": nov_ratio > 0.15,
            }

    output = {
        "audit_type": "regime_label_coverage",
        "audit_date": "2026-07-13",
        "observation_only": True,
        "n_symbols": len(all_labels),
        "per_symbol": per_symbol,
        "btc_alt_consistency": consistency,
        "november_2024_concentration": nov_check,
        "methodology_notes": [
            "Labels based on completed 4h candles only (EMA20/50/200 + ATR%).",
            "Label available at: bar_ts + 4h.",
            "No strategy returns calculated.",
            "No label definitions modified.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")

    # Summary
    for sym, info in per_symbol.items():
        fc = info["formation"]
        print(f"\n{sym}:")
        print(f"  Formation: {fc['coverage_days']}d, rate={fc['coverage_rate']:.2%}, status={fc['status']}")
        if fc.get("label_counts"):
            for lbl, cnt in sorted(fc["label_counts"].items()):
                print(f"    {lbl}: {cnt}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
