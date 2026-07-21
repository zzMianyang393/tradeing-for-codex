"""Range-regime funding extreme event audit.

Hypothesis: when a coin's funding rate hits a rolling-percentile extreme
while the market is in a "震荡" (range-bound) regime, the price may
subsequently mean-revert.

This is an event study, NOT a strategy.  No parameter sweep.
Thresholds are fixed.  Pass/fail is final.

Timing rules:
  - Regime label: based on completed 4h candle.  Available at 4h close.
  - Funding: settlements at 00:00, 08:00, 16:00 UTC.
  - Signal: funding extreme AND regime == "震荡", both confirmed.
  - Entry: next 15m bar open AFTER the later of (funding settlement, 4h close).
  - No look-ahead: only use data available at signal time.

Data: OKX funding + OKX 15m OHLCV only.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, stdev

from market import Bar, add_features, resample_minutes
from regime_validation import label_completed_4h_bars


DATA_DIR = Path("data")
COST_RT = 0.0016  # 0.05% taker + 0.03% slippage, round-trip
ROLLING_WINDOW_DAYS = 30  # rolling percentile window
EXTREME_PERCENTILE = 0.95  # top/bottom 5%
MIN_EVENTS_PER_LAYER = 15
HOLD_HORIZONS = [1, 4, 16, 96]  # 15m, 1h, 4h, 24h


# ── data loaders ─────────────────────────────────────────────────────────────

def load_ohlcv_15m(symbol: str) -> list[dict]:
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
                rows.append({
                    "ts": ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                })
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def load_funding(symbol: str) -> list[dict]:
    path = DATA_DIR / f"{symbol}_funding.csv"
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                rows.append({
                    "ts": int(row["timestamp_ms"]),
                    "rate": float(row["funding_rate"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
    return rows


# ── regime labeling (self-contained, no import of regime_validation) ─────────

FOUR_H_MS = 4 * 3600 * 1000


def resample_4h(bars_15m: list[dict]) -> list[dict]:
    """Resample 15m bars to 4h bars (open of first, close of last, H/L extremes)."""
    buckets: dict[int, list[dict]] = {}
    for b in bars_15m:
        bucket_ts = (b["ts"] // FOUR_H_MS) * FOUR_H_MS
        buckets.setdefault(bucket_ts, []).append(b)

    result: list[dict] = []
    for bucket_ts in sorted(buckets):
        group = buckets[bucket_ts]
        result.append({
            "ts": bucket_ts,
            "open": group[0]["open"],
            "high": max(g["high"] for g in group),
            "low": min(g["low"] for g in group),
            "close": group[-1]["close"],
            "volume": sum(g["volume"] for g in group),
        })
    return result


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float]:
    if len(highs) < 2:
        return [0.0] * len(highs)
    trs = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    return _ema(trs, period)


def label_4h_bars(bars_4h: list[dict]) -> list[tuple[int, str]]:
    """Return (availability_ts, label) for each completed 4h bar.

    availability_ts = bar close time = bar_ts + 4h.
    Label is one of: "趋势上行", "趋势下行", "高波动转换", "震荡".
    """
    if len(bars_4h) < 200:  # need enough for EMA200
        return []

    closes = [b["close"] for b in bars_4h]
    highs = [b["high"] for b in bars_4h]
    lows = [b["low"] for b in bars_4h]

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    atr = _atr(highs, lows, closes, 14)

    labels: list[tuple[int, str]] = []
    for i in range(len(bars_4h)):
        if i < 199:
            continue  # not enough data for EMA200

        atr_pct = atr[i] / closes[i] if closes[i] > 0 else 0

        # trend_strength approximation: (ema20 - ema200) / atr
        ts_val = (ema20[i] - ema200[i]) / atr[i] if atr[i] > 0 else 0

        if ema20[i] > ema50[i] > ema200[i] and ts_val >= 1.0:
            label = "趋势上行"
        elif ema20[i] < ema50[i] < ema200[i] and ts_val <= -1.0:
            label = "趋势下行"
        elif atr_pct >= 0.03:
            label = "高波动转换"
        else:
            label = "震荡"

        avail_ts = bars_4h[i]["ts"] + FOUR_H_MS
        labels.append((avail_ts, label))

    return labels


def labels_from_ohlcv_15m(bars_15m: list[dict]) -> list[tuple[int, str]]:
    """Use the project-standard completed-4h regime labels."""
    market_bars = [
        Bar(
            ts=bar["ts"],
            time=datetime.fromtimestamp(bar["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            open=bar["open"],
            high=bar["high"],
            low=bar["low"],
            close=bar["close"],
            volume_quote=bar["volume"] * bar["close"],
        )
        for bar in bars_15m
    ]
    return label_completed_4h_bars(add_features(resample_minutes(market_bars, 15)))


def regime_at(labels: list[tuple[int, str]], ts: int) -> str | None:
    """Return the regime label available at `ts`, or None."""
    if not labels:
        return None
    avail = [l[0] for l in labels]
    # bisect_right: find last label whose availability <= ts
    idx = 0
    for i, a in enumerate(avail):
        if a <= ts:
            idx = i
        else:
            break
    return labels[idx][1] if avail[idx] <= ts else None


# ── rolling percentile (no look-ahead) ───────────────────────────────────────

def rolling_percentile(values: list[float], window: int, pct: float) -> list[float | None]:
    """For each position, compute the percentile using only the `window` prior values.

    Returns None for positions < window.
    """
    result: list[float | None] = []
    for i in range(len(values)):
        if i < window:
            result.append(None)
        else:
            window_vals = values[i - window:i]
            sorted_w = sorted(window_vals)
            idx = min(len(sorted_w) - 1, int(len(sorted_w) * pct))
            result.append(sorted_w[idx])
    return result


# ── main audit ───────────────────────────────────────────────────────────────

def audit_symbol(
    symbol: str,
    ohlcv: list[dict],
    funding: list[dict],
    formation_start_ts: int,
    formation_end_ts: int,
) -> list[dict]:
    """Run event audit for one symbol within the formation period."""
    labels = labels_from_ohlcv_15m(ohlcv)
    if not labels:
        return []

    # Build funding lookup by settlement ts
    funding_map: dict[int, float] = {f["ts"]: f["rate"] for f in funding}

    # Build OHLCV lookup by ts
    ohlcv_map: dict[int, dict] = {b["ts"]: b for b in ohlcv}
    ohlcv_ts_sorted = sorted(ohlcv_map.keys())

    # For rolling percentile: collect all funding rates up to formation end
    funding_ts_sorted = sorted(f["ts"] for f in funding if f["ts"] <= formation_end_ts)
    funding_rate_series = [funding_map[ts] for ts in funding_ts_sorted]

    # Rolling percentile thresholds (no look-ahead)
    upper_thresholds = rolling_percentile(funding_rate_series, ROLLING_WINDOW_DAYS * 3, EXTREME_PERCENTILE)
    lower_thresholds = rolling_percentile(funding_rate_series, ROLLING_WINDOW_DAYS * 3, 1 - EXTREME_PERCENTILE)

    events: list[dict] = []
    for i, fts in enumerate(funding_ts_sorted):
        if not (formation_start_ts <= fts <= formation_end_ts):
            continue

        rate = funding_rate_series[i]
        upper = upper_thresholds[i]
        lower = lower_thresholds[i]
        if upper is None or lower is None:
            continue

        # Check if funding is extreme
        if rate >= upper:
            extreme_direction = "high"
        elif rate <= lower:
            extreme_direction = "low"
        else:
            continue

        # Check regime at funding settlement time
        regime = regime_at(labels, fts)
        if regime != "震荡":
            continue

        # Signal available at: max(funding settlement, latest 4h close)
        # Funding settlement is at fts.  4h close availability is at the
        # label's availability_ts.  The regime_at function already ensures
        # the label is available at fts, so signal_ts = fts.
        signal_ts = fts

        # Entry: next 15m bar after signal_ts
        entry_idx = None
        for j, ots in enumerate(ohlcv_ts_sorted):
            if ots > signal_ts:
                entry_idx = j
                break
        if entry_idx is None:
            continue

        entry_ts = ohlcv_ts_sorted[entry_idx]
        entry_price = ohlcv_map[entry_ts]["open"]

        # Forward returns
        fwd: dict[str, dict] = {}
        for h in HOLD_HORIZONS:
            exit_idx = entry_idx + h
            if exit_idx >= len(ohlcv_ts_sorted):
                continue
            exit_ts = ohlcv_ts_sorted[exit_idx]
            exit_price = ohlcv_map[exit_ts]["close"]
            price_ret_pct = (exit_price / entry_price - 1.0) * 100
            # Mean-reversion direction: high funding expects short price
            # reversion; low funding expects long price reversion.
            directional_ret_pct = -price_ret_pct if extreme_direction == "high" else price_ret_pct
            net_ret = directional_ret_pct - COST_RT * 100
            fwd[f"fwd_{h}bar"] = {
                "price_ret_pct": round(price_ret_pct, 4),
                "mean_reversion_ret_pct": round(directional_ret_pct, 4),
                "net_ret_pct": round(net_ret, 4),
            }

        events.append({
            "funding_ts": fts,
            "funding_rate": round(rate, 8),
            "extreme_direction": extreme_direction,
            "rolling_upper": round(upper, 8),
            "rolling_lower": round(lower, 8),
            "regime": regime,
            "signal_ts": signal_ts,
            "entry_ts": entry_ts,
            "entry_price": round(entry_price, 4),
            "forward_returns": fwd,
        })

    return events


def summarise_events(events: list[dict]) -> dict:
    """Aggregate event statistics."""
    if not events:
        return {"n_events": 0}

    fwd_stats: dict[str, dict] = {}
    for h in HOLD_HORIZONS:
        key = f"fwd_{h}bar"
        rets = [e["forward_returns"][key]["net_ret_pct"] for e in events if key in e["forward_returns"]]
        if not rets:
            continue
        fwd_stats[key] = {
            "n": len(rets),
            "mean_net_pct": round(mean(rets), 4),
            "median_net_pct": round(median(rets), 4),
            "stdev_net_pct": round(stdev(rets), 4) if len(rets) > 1 else 0,
            "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 3),
            "positive": sum(1 for r in rets if r > 0),
            "negative": sum(1 for r in rets if r <= 0),
        }

    months = Counter(datetime.fromtimestamp(e["funding_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m") for e in events)
    directions = Counter(e["extreme_direction"] for e in events)

    return {
        "n_events": len(events),
        "direction_breakdown": dict(directions),
        "month_distribution": dict(sorted(months.items())),
        "max_month_pct": round(max(months.values()) / len(events), 3),
        "forward_returns": fwd_stats,
    }


def verdict(summary: dict) -> tuple[str, list[str]]:
    """Apply pre-registered pass/fail criteria."""
    reasons: list[str] = []
    passed = True

    n = summary.get("n_events", 0)
    if n < MIN_EVENTS_PER_LAYER:
        reasons.append(f"events {n} < {MIN_EVENTS_PER_LAYER}")
        passed = False

    # Use 4h horizon for primary check
    r4 = summary.get("forward_returns", {}).get("fwd_16bar", {})
    if r4:
        if r4.get("mean_net_pct", 0) <= 0:
            reasons.append(f"4h net mean {r4['mean_net_pct']:+.4f}% <= 0")
            passed = False
        if r4.get("win_rate", 0) < 0.55:
            reasons.append(f"4h win rate {r4['win_rate']:.1%} < 55%")
            passed = False

    mc = summary.get("max_month_pct", 0)
    if mc > 0.30:
        reasons.append(f"month concentration {mc:.1%} > 30%")
        passed = False

    return ("通过形成期" if passed else "淘汰"), reasons


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Range-regime funding extreme event audit.")
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
    p.add_argument("--out", type=Path, default=Path("reports/range_regime_funding_extreme_audit.json"))
    args = p.parse_args(argv)

    def ts(date_str: str) -> int:
        return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

    fs, fe = ts(args.formation_start), ts(args.formation_end)

    print("Loading data and auditing...")
    all_events: list[dict] = []
    per_symbol: dict[str, dict] = {}

    for sym in args.symbols:
        ohlcv = load_ohlcv_15m(sym.split("-")[0])
        funding = load_funding(sym)
        if not ohlcv or not funding:
            continue

        events = audit_symbol(sym, ohlcv, funding, fs, fe)
        if events:
            all_events.extend(events)
            per_symbol[sym] = summarise_events(events)
            print(f"  {sym}: {len(events)} events")

    print(f"\nTotal events: {len(all_events)}")

    # Overall summary
    overall = summarise_events(all_events)
    v, reasons = verdict(overall)

    # Per-direction breakdown
    high_events = [e for e in all_events if e["extreme_direction"] == "high"]
    low_events = [e for e in all_events if e["extreme_direction"] == "low"]
    high_summary = summarise_events(high_events) if high_events else {"n_events": 0}
    low_summary = summarise_events(low_events) if low_events else {"n_events": 0}

    # Coin breakdown
    coin_stats: dict[str, dict] = {}
    for sym, stats in per_symbol.items():
        r4 = stats.get("forward_returns", {}).get("fwd_16bar", {})
        coin_stats[sym] = {
            "n_events": stats["n_events"],
            "4h_mean_net_pct": r4.get("mean_net_pct", 0),
            "4h_win_rate": r4.get("win_rate", 0),
        }

    report = {
        "audit_type": "range_regime_funding_extreme",
        "hypothesis": "funding extreme in 震荡 regime → mean reversion",
        "timing": "entry at next 15m after funding settlement, regime confirmed",
        "cost": "0.16% round trip",
        "rolling_window_days": ROLLING_WINDOW_DAYS,
        "extreme_percentile": EXTREME_PERCENTILE,
        "formation_period": f"{args.formation_start} to {args.formation_end}",
        "n_symbols": len(per_symbol),
        "overall": overall,
        "high_funding_extreme": high_summary,
        "low_funding_extreme": low_summary,
        "per_symbol": coin_stats,
        "verdict": v,
        "verdict_reasons": reasons,
        "methodology_notes": [
            "Regime label: project-standard regime_validation.label_completed_4h_bars.",
            "Label available at: 4h close time (bar_ts + 4h).",
            "Funding: only settlements at or before signal time.",
            "Rolling percentile: 90-settlement window (~30 days), no look-ahead.",
            "Entry: next 15m bar open after funding settlement.",
            "If any regime layer < 15 events, audit stops for that layer.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")

    print(f"\n{'='*60}")
    print(f"Verdict: {v}")
    for r in reasons:
        print(f"  - {r}")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
