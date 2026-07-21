"""Cross-time stability meta-audit.

Compares data characteristics between two non-overlapping time windows
to detect regime shifts, data quality degradation, or instability that
could invalidate future strategy research.

This is a META-AUDIT. It does NOT:
- Create strategies or signals
- Generate buy/sell recommendations
- Optimize parameters
- Output strategy returns

It ONLY outputs stability classifications and a decision table.

Data: Only free, public, OKX-native data passing research_data_gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev, median
from typing import Any


DATA_DIR = Path("data")


# ─── OHLCV helpers ───────────────────────────────────────────────────────────

def load_ohlcv_15m(symbol: str) -> list[dict]:
    """Load 15m OHLCV. Returns [{ts, open, high, low, close, volume}]."""
    path = DATA_DIR / f"{symbol}_15m.csv"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                if "timestamp_ms" in row:
                    ts = int(row["timestamp_ms"])
                else:
                    ts = int(
                        datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                        .replace(tzinfo=timezone.utc)
                        .timestamp()
                        * 1000
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


def compute_ohlcv_stats(rows: list[dict]) -> dict[str, Any]:
    """Compute distribution and quality stats for a window of OHLCV bars."""
    if len(rows) < 2:
        return {"error": "insufficient data"}

    # 15m returns
    returns = []
    for i in range(1, len(rows)):
        if rows[i - 1]["close"] > 0:
            returns.append((rows[i]["close"] / rows[i - 1]["close"] - 1.0) * 100)

    # Daily volume (sum of 15m volumes per UTC day)
    daily_vol: dict[str, float] = {}
    for r in rows:
        day = datetime.fromtimestamp(r["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        daily_vol[day] = daily_vol.get(day, 0) + r["volume"]

    volumes = list(daily_vol.values())

    def q(data: list[float], p: float) -> float:
        if not data:
            return 0.0
        s = sorted(data)
        return s[min(len(s) - 1, int(len(s) * p))]

    # Missing bars: expected ~96 per day, check gaps
    days_set = set()
    for r in rows:
        days_set.add(datetime.fromtimestamp(r["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"))
    n_days = len(days_set)
    expected_bars = n_days * 96
    missing_rate = max(0, 1 - len(rows) / expected_bars) if expected_bars > 0 else 0

    return {
        "n_bars": len(rows),
        "n_days": n_days,
        "return_mean": round(mean(returns), 6) if returns else 0,
        "return_stdev": round(stdev(returns), 6) if len(returns) > 1 else 0,
        "return_skew": round(_skew(returns), 4) if len(returns) > 2 else 0,
        "return_kurtosis": round(_kurtosis(returns), 4) if len(returns) > 3 else 0,
        "return_q05": round(q(returns, 0.05), 6),
        "return_q95": round(q(returns, 0.95), 6),
        "daily_volume_mean": round(mean(volumes), 2) if volumes else 0,
        "daily_volume_stdev": round(stdev(volumes), 2) if len(volumes) > 1 else 0,
        "daily_volume_median": round(median(volumes), 2) if volumes else 0,
        "missing_bar_rate": round(missing_rate, 4),
    }


def _skew(data: list[float]) -> float:
    n = len(data)
    if n < 3:
        return 0.0
    m = mean(data)
    s = stdev(data)
    if s == 0:
        return 0.0
    return (n / ((n - 1) * (n - 2))) * sum(((x - m) / s) ** 3 for x in data)


def _kurtosis(data: list[float]) -> float:
    n = len(data)
    if n < 4:
        return 0.0
    m = mean(data)
    s = stdev(data)
    if s == 0:
        return 0.0
    k4 = sum(((x - m) / s) ** 4 for x in data) / n
    return k4 - 3  # excess kurtosis


def compute_cross_coin_correlation(symbols: list[str], rows_map: dict[str, list[dict]]) -> dict[str, Any]:
    """Compute average pairwise correlation of 15m returns across coins."""
    # Build return series for each symbol (resample to hourly for speed)
    hourly_returns: dict[str, list[float]] = {}
    for sym in symbols:
        rows = rows_map.get(sym, [])
        if len(rows) < 100:
            continue
        # Resample to hourly (4 x 15m)
        hourly: dict[int, dict] = {}
        for r in rows:
            bucket = (r["ts"] // 3600000) * 3600000
            hourly[bucket] = r  # last value in hour
        ts_sorted = sorted(hourly.keys())
        rets = []
        for i in range(1, len(ts_sorted)):
            prev = hourly[ts_sorted[i - 1]]["close"]
            curr = hourly[ts_sorted[i]]["close"]
            if prev > 0:
                rets.append((curr / prev - 1.0) * 100)
        if len(rets) >= 100:
            hourly_returns[sym] = rets

    # Compute pairwise correlations
    syms = sorted(hourly_returns.keys())
    pairs = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            r1 = hourly_returns[syms[i]]
            r2 = hourly_returns[syms[j]]
            n = min(len(r1), len(r2))
            if n < 50:
                continue
            corr = _pearson(r1[:n], r2[:n])
            if not math.isnan(corr):
                pairs.append({"pair": f"{syms[i]}-{syms[j]}", "corr": round(corr, 4)})

    if not pairs:
        return {"n_pairs": 0, "mean_corr": 0, "median_corr": 0}

    corrs = [p["corr"] for p in pairs]
    return {
        "n_pairs": len(pairs),
        "mean_corr": round(mean(corrs), 4),
        "median_corr": round(median(corrs), 4),
        "min_corr": round(min(corrs), 4),
        "max_corr": round(max(corrs), 4),
    }


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 3:
        return float("nan")
    mx, my = mean(x), mean(y)
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (n - 1)
    sx = stdev(x)
    sy = stdev(y)
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


# ─── Funding helpers ─────────────────────────────────────────────────────────

def load_funding(symbol: str) -> list[dict]:
    """Load funding rates. Returns [{ts, rate}]."""
    path = DATA_DIR / f"{symbol}_funding.csv"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["timestamp_ms"])
                rows.append({"ts": ts, "rate": float(row["funding_rate"])})
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def compute_funding_stats(rows: list[dict]) -> dict[str, Any]:
    """Compute funding rate distribution and quality stats."""
    if len(rows) < 10:
        return {"error": "insufficient data"}

    rates = [r["rate"] for r in rows]
    n_days = len(set(
        datetime.fromtimestamp(r["ts"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        for r in rows
    ))

    def q(data: list[float], p: float) -> float:
        s = sorted(data)
        return s[min(len(s) - 1, int(len(s) * p))]

    # Extreme values: |rate| > 0.1% (0.001)
    extreme_count = sum(1 for r in rates if abs(r) > 0.001)
    # Negative funding days
    negative_count = sum(1 for r in rates if r < 0)

    # Expected settlements: 3 per day
    expected = n_days * 3
    coverage = len(rows) / expected if expected > 0 else 0

    return {
        "n_records": len(rows),
        "n_days": n_days,
        "mean_rate": round(mean(rates), 6),
        "stdev_rate": round(stdev(rates), 6) if len(rates) > 1 else 0,
        "median_rate": round(median(rates), 6),
        "q05": round(q(rates, 0.05), 6),
        "q95": round(q(rates, 0.95), 6),
        "min": round(min(rates), 6),
        "max": round(max(rates), 6),
        "extreme_count": extreme_count,
        "extreme_rate": round(extreme_count / len(rates), 4),
        "negative_count": negative_count,
        "negative_rate": round(negative_count / len(rates), 4),
        "coverage": round(coverage, 4),
    }


# ─── OI helpers ──────────────────────────────────────────────────────────────

def load_oi_daily(symbol: str) -> list[dict]:
    """Load daily OI. Returns [{ts, oi_usd}]."""
    path = DATA_DIR / f"{symbol}_open_interest_1d.csv"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["ts"])
                rows.append({"ts": ts, "oi_usd": float(row["open_interest_usd"])})
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def compute_oi_stats(rows: list[dict]) -> dict[str, Any]:
    """Compute OI distribution and quality stats."""
    if len(rows) < 10:
        return {"error": "insufficient data"}

    oi_values = [r["oi_usd"] for r in rows]

    # Daily changes
    changes = []
    for i in range(1, len(rows)):
        if rows[i - 1]["oi_usd"] > 0:
            changes.append((rows[i]["oi_usd"] / rows[i - 1]["oi_usd"] - 1.0) * 100)

    def q(data: list[float], p: float) -> float:
        s = sorted(data)
        return s[min(len(s) - 1, int(len(s) * p))]

    # Extreme changes: > 10% daily
    extreme_changes = sum(1 for c in changes if abs(c) > 10)

    # Coverage: expected 1 per day
    n_days = len(rows)
    date_range = (rows[-1]["ts"] - rows[0]["ts"]) / 86400000
    coverage = n_days / date_range if date_range > 0 else 0

    return {
        "n_records": len(rows),
        "n_days": n_days,
        "mean_oi_usd": round(mean(oi_values), 2),
        "stdev_oi_usd": round(stdev(oi_values), 2) if len(oi_values) > 1 else 0,
        "median_oi_usd": round(median(oi_values), 2),
        "q05": round(q(oi_values, 0.05), 2),
        "q95": round(q(oi_values, 0.95), 2),
        "mean_daily_change_pct": round(mean(changes), 4) if changes else 0,
        "stdev_daily_change_pct": round(stdev(changes), 4) if len(changes) > 1 else 0,
        "extreme_change_count": extreme_changes,
        "extreme_change_rate": round(extreme_changes / len(changes), 4) if changes else 0,
        "coverage": round(coverage, 4),
    }


# ─── Stability comparison ────────────────────────────────────────────────────

def classify_stability(
    window1: dict[str, Any],
    window2: dict[str, Any],
    metric: str,
    threshold_pct: float = 50.0,
    min_value: float = 0.0,
) -> str:
    """Classify a metric as stable/unstable/insufficient.

    A metric is "stable" if the relative change between windows is within threshold_pct%.
    A metric is "insufficient" if either window has an error or value below min_value.
    """
    v1 = window1.get(metric)
    v2 = window2.get(metric)

    if v1 is None or v2 is None:
        return "样本不足"
    if isinstance(v1, str) or isinstance(v2, str):
        return "样本不足"
    if "error" in window1 or "error" in window2:
        return "样本不足"

    # For rates/percentages, use absolute difference
    if metric.endswith("_rate") or metric.endswith("_pct") or "return_" in metric:
        diff = abs(v1 - v2)
        avg = (abs(v1) + abs(v2)) / 2
        if avg < 1e-10:
            return "稳定" if diff < 1e-6 else "不稳定"
        rel_diff = diff / avg * 100
    else:
        avg = (abs(v1) + abs(v2)) / 2
        if avg < min_value:
            return "样本不足"
        diff = abs(v1 - v2)
        rel_diff = diff / avg * 100

    if rel_diff <= threshold_pct:
        return "稳定"
    return "不稳定"


def compare_windows(
    w1: dict[str, Any],
    w2: dict[str, Any],
    metrics: list[str],
    threshold_pct: float = 50.0,
) -> dict[str, dict]:
    """Compare multiple metrics between two windows."""
    results = {}
    for metric in metrics:
        v1 = w1.get(metric)
        v2 = w2.get(metric)
        stability = classify_stability(w1, w2, metric, threshold_pct)
        results[metric] = {
            "window1": v1,
            "window2": v2,
            "stability": stability,
        }
        # Add relative change if both are numeric
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            avg = (abs(v1) + abs(v2)) / 2
            if avg > 1e-10:
                results[metric]["relative_change_pct"] = round((v2 - v1) / avg * 100, 2)
    return results


# ─── Main audit ──────────────────────────────────────────────────────────────

def audit_ohlcv(symbols: list[str], split_ratio: float = 0.5) -> dict[str, Any]:
    """Audit OHLCV stability across two time windows."""
    print(f"\n=== OHLCV Stability Audit ({len(symbols)} symbols) ===")

    all_stats_w1: list[dict] = []
    all_stats_w2: list[dict] = []
    per_symbol: dict[str, dict] = {}
    rows_map: dict[str, list[dict]] = {}

    for sym in symbols:
        rows = load_ohlcv_15m(sym)
        if len(rows) < 1000:
            continue
        rows_map[sym] = rows

        split_idx = int(len(rows) * split_ratio)
        w1 = compute_ohlcv_stats(rows[:split_idx])
        w2 = compute_ohlcv_stats(rows[split_idx:])

        all_stats_w1.append(w1)
        all_stats_w2.append(w2)
        per_symbol[sym] = {"window1": w1, "window2": w2}

    # Aggregate across symbols
    def aggregate_stats(stats_list: list[dict], key: str) -> float:
        values = [s[key] for s in stats_list if key in s and not isinstance(s.get(key), str)]
        return round(mean(values), 6) if values else 0

    agg_w1 = {k: aggregate_stats(all_stats_w1, k) for k in [
        "return_mean", "return_stdev", "return_skew", "return_kurtosis",
        "return_q05", "return_q95", "daily_volume_mean", "daily_volume_stdev",
        "missing_bar_rate",
    ]}
    agg_w2 = {k: aggregate_stats(all_stats_w2, k) for k in [
        "return_mean", "return_stdev", "return_skew", "return_kurtosis",
        "return_q05", "return_q95", "daily_volume_mean", "daily_volume_stdev",
        "missing_bar_rate",
    ]}

    # Cross-coin correlation per window
    split_ts_map: dict[str, int] = {}
    for sym, rows in rows_map.items():
        split_idx = int(len(rows) * split_ratio)
        split_ts_map[sym] = rows[split_idx]["ts"]

    # Use median split timestamp
    median_split_ts = sorted(split_ts_map.values())[len(split_ts_map) // 2]

    rows_map_w1 = {sym: [r for r in rows if r["ts"] < median_split_ts] for sym, rows in rows_map.items()}
    rows_map_w2 = {sym: [r for r in rows if r["ts"] >= median_split_ts] for sym, rows in rows_map.items()}

    corr_w1 = compute_cross_coin_correlation(symbols, rows_map_w1)
    corr_w2 = compute_cross_coin_correlation(symbols, rows_map_w2)

    # Stability comparison
    metrics = list(agg_w1.keys())
    stability = compare_windows(agg_w1, agg_w2, metrics, threshold_pct=50.0)

    # Correlation stability
    corr_stability = "稳定" if abs(corr_w1.get("mean_corr", 0) - corr_w2.get("mean_corr", 0)) < 0.2 else "不稳定"

    return {
        "n_symbols": len(rows_map),
        "split_ratio": split_ratio,
        "aggregate_window1": agg_w1,
        "aggregate_window2": agg_w2,
        "cross_coin_corr_window1": corr_w1,
        "cross_coin_corr_window2": corr_w2,
        "correlation_stability": corr_stability,
        "metric_stability": stability,
        "per_symbol_count": len(per_symbol),
    }


def audit_funding(symbols: list[str], split_ratio: float = 0.5) -> dict[str, Any]:
    """Audit funding rate stability across two time windows."""
    print(f"\n=== Funding Stability Audit ({len(symbols)} symbols) ===")

    all_stats_w1: list[dict] = []
    all_stats_w2: list[dict] = []
    per_symbol: dict[str, dict] = {}

    for sym in symbols:
        rows = load_funding(sym)
        if len(rows) < 100:
            continue

        split_idx = int(len(rows) * split_ratio)
        w1 = compute_funding_stats(rows[:split_idx])
        w2 = compute_funding_stats(rows[split_idx:])

        all_stats_w1.append(w1)
        all_stats_w2.append(w2)
        per_symbol[sym] = {"window1": w1, "window2": w2}

    def aggregate_stats(stats_list: list[dict], key: str) -> float:
        values = [s[key] for s in stats_list if key in s and not isinstance(s.get(key), str)]
        return round(mean(values), 6) if values else 0

    agg_w1 = {k: aggregate_stats(all_stats_w1, k) for k in [
        "mean_rate", "stdev_rate", "median_rate", "q05", "q95",
        "extreme_rate", "negative_rate", "coverage",
    ]}
    agg_w2 = {k: aggregate_stats(all_stats_w2, k) for k in [
        "mean_rate", "stdev_rate", "median_rate", "q05", "q95",
        "extreme_rate", "negative_rate", "coverage",
    ]}

    metrics = list(agg_w1.keys())
    stability = compare_windows(agg_w1, agg_w2, metrics, threshold_pct=50.0)

    return {
        "n_symbols": len(per_symbol),
        "split_ratio": split_ratio,
        "aggregate_window1": agg_w1,
        "aggregate_window2": agg_w2,
        "metric_stability": stability,
        "per_symbol_count": len(per_symbol),
    }


def audit_oi(symbols: list[str], split_ratio: float = 0.5) -> dict[str, Any]:
    """Audit OI stability across two time windows."""
    print(f"\n=== OI Stability Audit ({len(symbols)} symbols) ===")

    all_stats_w1: list[dict] = []
    all_stats_w2: list[dict] = []
    per_symbol: dict[str, dict] = {}

    for sym in symbols:
        rows = load_oi_daily(sym)
        if len(rows) < 100:
            continue

        split_idx = int(len(rows) * split_ratio)
        w1 = compute_oi_stats(rows[:split_idx])
        w2 = compute_oi_stats(rows[split_idx:])

        all_stats_w1.append(w1)
        all_stats_w2.append(w2)
        per_symbol[sym] = {"window1": w1, "window2": w2}

    def aggregate_stats(stats_list: list[dict], key: str) -> float:
        values = [s[key] for s in stats_list if key in s and not isinstance(s.get(key), str)]
        return round(mean(values), 6) if values else 0

    agg_w1 = {k: aggregate_stats(all_stats_w1, k) for k in [
        "mean_oi_usd", "stdev_oi_usd", "mean_daily_change_pct",
        "stdev_daily_change_pct", "extreme_change_rate", "coverage",
    ]}
    agg_w2 = {k: aggregate_stats(all_stats_w2, k) for k in [
        "mean_oi_usd", "stdev_oi_usd", "mean_daily_change_pct",
        "stdev_daily_change_pct", "extreme_change_rate", "coverage",
    ]}

    metrics = list(agg_w1.keys())
    stability = compare_windows(agg_w1, agg_w2, metrics, threshold_pct=50.0)

    return {
        "n_symbols": len(per_symbol),
        "split_ratio": split_ratio,
        "aggregate_window1": agg_w1,
        "aggregate_window2": agg_w2,
        "metric_stability": stability,
        "per_symbol_count": len(per_symbol),
    }


def build_decision_table(
    ohlcv_result: dict,
    funding_result: dict,
    oi_result: dict,
) -> list[dict]:
    """Build decision table: which data characteristics are stable enough for future research."""
    table = []

    # OHLCV metrics
    for metric, info in ohlcv_result.get("metric_stability", {}).items():
        table.append({
            "data_type": "ohlcv_15m",
            "metric": metric,
            "window1": info.get("window1"),
            "window2": info.get("window2"),
            "stability": info.get("stability", "样本不足"),
            "decision": _decision(info.get("stability", "样本不足"), "ohlcv"),
        })

    # OHLCV correlation
    corr_stab = ohlcv_result.get("correlation_stability", "样本不足")
    table.append({
        "data_type": "ohlcv_15m",
        "metric": "cross_coin_correlation",
        "window1": ohlcv_result.get("cross_coin_corr_window1", {}).get("mean_corr"),
        "window2": ohlcv_result.get("cross_coin_corr_window2", {}).get("mean_corr"),
        "stability": corr_stab,
        "decision": _decision(corr_stab, "ohlcv"),
    })

    # Funding metrics
    for metric, info in funding_result.get("metric_stability", {}).items():
        table.append({
            "data_type": "funding",
            "metric": metric,
            "window1": info.get("window1"),
            "window2": info.get("window2"),
            "stability": info.get("stability", "样本不足"),
            "decision": _decision(info.get("stability", "样本不足"), "funding"),
        })

    # OI metrics
    for metric, info in oi_result.get("metric_stability", {}).items():
        table.append({
            "data_type": "open_interest",
            "metric": metric,
            "window1": info.get("window1"),
            "window2": info.get("window2"),
            "stability": info.get("stability", "样本不足"),
            "decision": _decision(info.get("stability", "样本不足"), "oi"),
        })

    return table


def _decision(stability: str, data_type: str) -> str:
    """Map stability to research decision."""
    if stability == "稳定":
        return "可用作未来机制研究输入"
    elif stability == "不稳定":
        return "冻结：时间不稳定，不得作为单一窗口假设依据"
    else:
        return "冻结：样本不足，不得使用"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-time stability meta-audit.")
    parser.add_argument("--ohlcv-symbols", nargs="+", default=[
        "AAVE", "ADA", "APT", "ARB", "ATOM", "AVAX", "BNB", "BTC", "CRV",
        "DOGE", "DOT", "DYDX", "ETH", "FIL", "IMX", "INJ", "LINK", "LTC",
        "NEAR", "OP", "RENDER", "SEI", "SOL", "STX", "SUI", "TIA", "TRX", "UNI", "XRP",
    ])
    parser.add_argument("--funding-symbols", nargs="+", default=[
        "AAVE-USDT-SWAP", "ADA-USDT-SWAP", "APT-USDT-SWAP", "ARB-USDT-SWAP",
        "ATOM-USDT-SWAP", "AVAX-USDT-SWAP", "BTC-USDT-SWAP", "CRV-USDT-SWAP",
        "DOGE-USDT-SWAP", "DOT-USDT-SWAP", "DYDX-USDT-SWAP", "ETH-USDT-SWAP",
        "FIL-USDT-SWAP", "IMX-USDT-SWAP", "INJ-USDT-SWAP", "LINK-USDT-SWAP",
        "LTC-USDT-SWAP", "NEAR-USDT-SWAP", "OP-USDT-SWAP", "RENDER-USDT-SWAP",
        "STX-USDT-SWAP", "SUI-USDT-SWAP", "TIA-USDT-SWAP", "TRX-USDT-SWAP",
        "UNI-USDT-SWAP",
    ])
    parser.add_argument("--oi-symbols", nargs="+", default=[
        "AAVE-USDT-SWAP", "ADA-USDT-SWAP", "APT-USDT-SWAP", "ARB-USDT-SWAP",
        "ATOM-USDT-SWAP", "AVAX-USDT-SWAP", "BTC-USDT-SWAP", "CRV-USDT-SWAP",
        "DOGE-USDT-SWAP", "DOT-USDT-SWAP", "DYDX-USDT-SWAP", "ETH-USDT-SWAP",
        "FIL-USDT-SWAP", "IMX-USDT-SWAP", "INJ-USDT-SWAP", "LINK-USDT-SWAP",
        "LTC-USDT-SWAP", "NEAR-USDT-SWAP", "OP-USDT-SWAP", "RENDER-USDT-SWAP",
        "STX-USDT-SWAP", "SUI-USDT-SWAP", "TIA-USDT-SWAP", "TRX-USDT-SWAP",
        "UNI-USDT-SWAP",
    ])
    parser.add_argument("--split-ratio", type=float, default=0.5, help="Split point as fraction of data")
    parser.add_argument("--out", type=Path, default=Path("reports/cross_time_stability_audit.json"))
    args = parser.parse_args(argv)

    ohlcv_result = audit_ohlcv(args.ohlcv_symbols, args.split_ratio)
    funding_result = audit_funding(args.funding_symbols, args.split_ratio)
    oi_result = audit_oi(args.oi_symbols, args.split_ratio)

    decision_table = build_decision_table(ohlcv_result, funding_result, oi_result)

    # Summary
    stable_count = sum(1 for d in decision_table if d["stability"] == "稳定")
    unstable_count = sum(1 for d in decision_table if d["stability"] == "不稳定")
    insufficient_count = sum(1 for d in decision_table if d["stability"] == "样本不足")

    report = {
        "audit_type": "cross_time_stability_meta_audit",
        "audit_date": "2026-07-12",
        "data_source": "OKX native, research_data_gate eligible only",
        "split_ratio": args.split_ratio,
        "summary": {
            "total_metrics": len(decision_table),
            "stable": stable_count,
            "unstable": unstable_count,
            "insufficient": insufficient_count,
        },
        "ohlcv_audit": {
            "n_symbols": ohlcv_result["n_symbols"],
            "metric_stability": ohlcv_result["metric_stability"],
            "correlation_stability": ohlcv_result["correlation_stability"],
            "cross_coin_corr": {
                "window1": ohlcv_result["cross_coin_corr_window1"],
                "window2": ohlcv_result["cross_coin_corr_window2"],
            },
        },
        "funding_audit": {
            "n_symbols": funding_result["n_symbols"],
            "metric_stability": funding_result["metric_stability"],
        },
        "oi_audit": {
            "n_symbols": oi_result["n_symbols"],
            "metric_stability": oi_result["metric_stability"],
        },
        "decision_table": decision_table,
        "methodology_notes": [
            "数据按时间中点分割为前后两个不重叠窗口",
            "稳定性阈值：前后窗口相对变化 <= 50% 为稳定",
            "收益分布指标（均值、标准差等）使用绝对差异而非相对差异",
            "跨币种相关性使用小时收益计算皮尔逊相关系数",
            "所有指标仅使用截至窗口结束时的已知数据，无前视偏差",
            "OI 日度数据时间戳为 16:00 UTC；funding 为 00:00/08:00/16:00 UTC",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")

    # Print summary
    print(f"\n=== Summary ===")
    print(f"Total metrics: {len(decision_table)}")
    print(f"Stable: {stable_count}")
    print(f"Unstable: {unstable_count}")
    print(f"Insufficient: {insufficient_count}")
    print(f"\nDecision table:")
    for d in decision_table:
        print(f"  {d['data_type']:15s} {d['metric']:30s} {d['stability']:8s} -> {d['decision']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
