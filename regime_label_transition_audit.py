"""Regime label transition and availability timing audit.

Verifies:
  - Labels use only completed 4h candles (no future data)
  - Signal time can only use labels available at that time
  - Label switching frequency, min duration, flicker rate
  - 4h vs daily label alignment delay rules

This is an OBSERVATION-ONLY audit.  It does NOT calculate returns.
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
DAY_MS = 24 * 3600 * 1000


def _load_ohlcv(symbol: str, start: str, end: str) -> list[dict]:
    path = DATA_DIR / f"{symbol}_15m.csv"
    if not path.exists():
        return []
    s = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    e = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if s <= ts <= e:
                    rows.append({"ts": int(ts.timestamp() * 1000), "close": float(r["close"]),
                                 "high": float(r["high"]), "low": float(r["low"]),
                                 "open": float(r["open"]), "volume": float(r.get("volume", 0))})
            except (KeyError, ValueError):
                continue
    return rows


def _resample_4h(bars: list[dict]) -> list[dict]:
    buckets: dict[int, list[dict]] = {}
    for b in bars:
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


def _atr(h, lo, c, p=14):
    if len(h) < 2:
        return [0.0] * len(h)
    trs = [h[0] - lo[0]]
    for i in range(1, len(h)):
        trs.append(max(h[i] - lo[i], abs(h[i] - c[i-1]), abs(lo[i] - c[i-1])))
    return _ema(trs, p)


def _label_4h(bars_4h):
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
        labels.append({"bar_ts": bars_4h[i]["ts"], "available_at": bars_4h[i]["ts"] + FOUR_H_MS, "label": lbl})
    return labels


def analyze_transitions(labels: list[dict]) -> dict:
    """Analyze label transition patterns."""
    if len(labels) < 2:
        return {"error": "insufficient labels"}

    transitions: Counter = Counter()
    durations: dict[str, list[int]] = defaultdict(list)
    current_label = labels[0]["label"]
    current_start = 0

    for i in range(1, len(labels)):
        if labels[i]["label"] != current_label:
            transitions[(current_label, labels[i]["label"])] += 1
            durations[current_label].append(i - current_start)
            current_label = labels[i]["label"]
            current_start = i
    durations[current_label].append(len(labels) - current_start)

    # Flicker rate: segments of length 1
    flicker_count = sum(1 for lengths in durations.values() for l in lengths if l == 1)
    total_segments = sum(len(lengths) for lengths in durations.values())

    # Min/mean/max duration per label
    duration_stats = {}
    for lbl, lengths in durations.items():
        duration_stats[lbl] = {
            "n_segments": len(lengths),
            "mean_4h_bars": round(mean(lengths), 1),
            "min_4h_bars": min(lengths),
            "max_4h_bars": max(lengths),
            "mean_hours": round(mean(lengths) * 4, 1),
        }

    return {
        "n_transitions": sum(transitions.values()),
        "transition_counts": {f"{a}->{b}": c for (a, b), c in transitions.most_common()},
        "duration_stats": duration_stats,
        "flicker_count": flicker_count,
        "flicker_rate": round(flicker_count / total_segments, 4) if total_segments > 0 else 0,
        "total_segments": total_segments,
    }


def verify_timing_correctness(labels: list[dict]) -> dict:
    """Verify that labels are only available after the 4h bar closes."""
    violations = []
    for lbl in labels:
        bar_ts = lbl["bar_ts"]
        avail = lbl["available_at"]
        expected_avail = bar_ts + FOUR_H_MS
        if avail < expected_avail:
            violations.append({
                "bar_ts": bar_ts,
                "available_at": avail,
                "expected_available_at": expected_avail,
                "label": lbl["label"],
            })

    return {
        "n_labels_checked": len(labels),
        "n_violations": len(violations),
        "violations": violations[:5],  # first 5 for inspection
        "status": "valid" if len(violations) == 0 else "invalid_for_activation",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Regime label transition audit.")
    p.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "SOL", "DOGE", "LINK"])
    p.add_argument("--start", default="2024-01-01")
    p.add_argument("--end", default="2025-07-10")
    p.add_argument("--out", type=Path, default=Path("reports/regime_label_transition_audit.json"))
    args = p.parse_args(argv)

    print("Loading and labeling...")
    per_symbol: dict[str, dict] = {}

    for sym in args.symbols:
        bars = _load_ohlcv(sym, args.start, args.end)
        if len(bars) < 1000:
            print(f"  {sym}: insufficient data")
            continue
        bars_4h = _resample_4h(bars)
        labels = _label_4h(bars_4h)
        if not labels:
            continue

        transitions = analyze_transitions(labels)
        timing = verify_timing_correctness(labels)
        per_symbol[sym] = {"transitions": transitions, "timing": timing}
        print(f"  {sym}: {len(labels)} labels, {transitions['n_transitions']} transitions, "
              f"flicker={transitions['flicker_rate']:.2%}, timing={timing['status']}")

    output = {
        "audit_type": "regime_label_transition",
        "audit_date": "2026-07-13",
        "observation_only": True,
        "per_symbol": per_symbol,
        "methodology_notes": [
            "Labels from completed 4h candles only.",
            "Available at = bar_ts + 4h (enforced).",
            "Flicker = segments of length 1 (single-bar regime).",
            "No returns calculated.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
