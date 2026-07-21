"""Daily OI deleveraging filter meta-audit.

This is meta-only research infrastructure.  It does not produce an entry
signal.  It asks whether a daily high-leverage state, measured by OI relative
to trailing 24h traded notional, identifies periods with unusually large
forward shocks.

Timing:
  - daily OI snapshots are treated as available at 16:00 UTC
  - trailing volume uses only 15m bars ending at or before 16:00 UTC
  - forward returns enter at 16:15 UTC
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


FIFTEEN_MINUTES_MS = 15 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
LOOKBACK_DAYS = 180
OIVR_PERCENTILE = 0.80
MIN_OI_7D_CHANGE = 0.05


@dataclass(frozen=True)
class OiRow:
    symbol: str
    ts: int
    timestamp_utc: str
    open_interest_usd: float


@dataclass(frozen=True)
class PriceBar:
    ts: int
    open: float
    close: float
    volume: float


@dataclass(frozen=True)
class LeverageState:
    symbol: str
    split: str
    oi_ts: int
    timestamp_utc: str
    entry_ts: int
    entry_timestamp_utc: str
    oivr: float
    oivr_threshold: float
    oi_7d_change_pct: float
    trailing_24h_notional: float
    fwd_1d_return_pct: float
    fwd_3d_return_pct: float
    fwd_7d_return_pct: float
    fwd_3d_abs_return_pct: float
    fwd_7d_abs_return_pct: float


def parse_timestamp_ms(value: str) -> int:
    stripped = value.strip()
    if stripped.isdigit():
        raw = int(stripped)
        return raw * 1000 if raw < 10_000_000_000 else raw
    return int(datetime.strptime(stripped, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * q))
    return ordered[index]


def load_oi(path: Path) -> list[OiRow]:
    symbol = path.name.replace("_open_interest_1d.csv", "")
    rows: list[OiRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                ts = int(row["ts"])
                value = float(row["open_interest_usd"])
                if value <= 0:
                    continue
                rows.append(OiRow(symbol, ts, row.get("timestamp_utc") or format_utc(ts), value))
            except (KeyError, TypeError, ValueError):
                continue
    rows.sort(key=lambda item: item.ts)
    return rows


def load_price_bars(path: Path) -> list[PriceBar]:
    bars: list[PriceBar] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                raw_ts = row.get("timestamp_ms") or row.get("timestamp")
                if raw_ts is None:
                    continue
                ts = parse_timestamp_ms(raw_ts)
                bars.append(
                    PriceBar(
                        ts=ts,
                        open=float(row["open"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0.0),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    bars.sort(key=lambda item: item.ts)
    return bars


def discover_symbols(data_dir: Path) -> list[str]:
    symbols: list[str] = []
    for path in sorted(data_dir.glob("*-USDT-SWAP_open_interest_1d.csv")):
        symbol = path.name.replace("_open_interest_1d.csv", "")
        base = symbol.split("-", 1)[0]
        if (data_dir / f"{base}_15m.csv").exists():
            symbols.append(symbol)
    return symbols


def trailing_notional(bars: list[PriceBar], cutoff_ts: int) -> float:
    start_ts = cutoff_ts - DAY_MS
    return sum(bar.volume * bar.close for bar in bars if start_ts < bar.ts <= cutoff_ts and bar.close > 0)


def price_at_or_after(lookup: dict[int, PriceBar], ts: int) -> PriceBar | None:
    bucket = ((ts + FIFTEEN_MINUTES_MS - 1) // FIFTEEN_MINUTES_MS) * FIFTEEN_MINUTES_MS
    for _ in range(96):
        bar = lookup.get(bucket)
        if bar is not None and bar.open > 0:
            return bar
        bucket += FIFTEEN_MINUTES_MS
    return None


def split_for_ts(ts: int, formation_end_ts: int) -> str:
    return "formation" if ts <= formation_end_ts else "oos"


def generate_states_for_symbol(
    symbol: str,
    oi_rows: list[OiRow],
    bars: list[PriceBar],
    formation_end_ts: int,
    oos_end_ts: int,
) -> list[LeverageState]:
    lookup = {bar.ts: bar for bar in bars}
    oivr_by_index: list[float | None] = []
    for row in oi_rows:
        notional = trailing_notional(bars, row.ts)
        oivr_by_index.append(row.open_interest_usd / notional if notional > 0 else None)

    states: list[LeverageState] = []
    for index in range(LOOKBACK_DAYS, len(oi_rows) - 7):
        row = oi_rows[index]
        if row.ts > oos_end_ts:
            continue
        oivr = oivr_by_index[index]
        if oivr is None:
            continue
        prior = [value for value in oivr_by_index[index - LOOKBACK_DAYS:index] if value is not None]
        if len(prior) < LOOKBACK_DAYS // 2:
            continue
        threshold = percentile(prior, OIVR_PERCENTILE)
        previous_7d_oi = oi_rows[index - 7].open_interest_usd
        if previous_7d_oi <= 0:
            continue
        oi_7d_change = row.open_interest_usd / previous_7d_oi - 1.0
        if oivr < threshold or oi_7d_change < MIN_OI_7D_CHANGE:
            continue

        entry_ts = row.ts + FIFTEEN_MINUTES_MS
        entry = price_at_or_after(lookup, entry_ts)
        exit_1d = price_at_or_after(lookup, entry_ts + DAY_MS)
        exit_3d = price_at_or_after(lookup, entry_ts + 3 * DAY_MS)
        exit_7d = price_at_or_after(lookup, entry_ts + 7 * DAY_MS)
        if entry is None or exit_1d is None or exit_3d is None or exit_7d is None:
            continue
        if exit_7d.ts > oos_end_ts:
            continue
        r1 = exit_1d.close / entry.open - 1.0
        r3 = exit_3d.close / entry.open - 1.0
        r7 = exit_7d.close / entry.open - 1.0
        states.append(
            LeverageState(
                symbol=symbol,
                split=split_for_ts(row.ts, formation_end_ts),
                oi_ts=row.ts,
                timestamp_utc=row.timestamp_utc,
                entry_ts=entry.ts,
                entry_timestamp_utc=format_utc(entry.ts),
                oivr=round(oivr, 10),
                oivr_threshold=round(threshold, 10),
                oi_7d_change_pct=round(oi_7d_change * 100.0, 6),
                trailing_24h_notional=round(trailing_notional(bars, row.ts), 6),
                fwd_1d_return_pct=round(r1 * 100.0, 6),
                fwd_3d_return_pct=round(r3 * 100.0, 6),
                fwd_7d_return_pct=round(r7 * 100.0, 6),
                fwd_3d_abs_return_pct=round(abs(r3) * 100.0, 6),
                fwd_7d_abs_return_pct=round(abs(r7) * 100.0, 6),
            )
        )
    return states


def summarize(values: list[float]) -> dict[str, float | int]:
    return {
        "observations": len(values),
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "median_pct": round(median(values), 6) if values else 0.0,
        "negative_rate": round(sum(value < 0 for value in values) / len(values), 6) if values else 0.0,
    }


def summarize_states(states: list[LeverageState]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for split in ("formation", "oos"):
        split_states = [state for state in states if state.split == split]
        output[split] = {
            "events": len(split_states),
            "fwd_1d": summarize([state.fwd_1d_return_pct for state in split_states]),
            "fwd_3d": summarize([state.fwd_3d_return_pct for state in split_states]),
            "fwd_7d": summarize([state.fwd_7d_return_pct for state in split_states]),
            "abs_fwd_3d": summarize([state.fwd_3d_abs_return_pct for state in split_states]),
            "abs_fwd_7d": summarize([state.fwd_7d_abs_return_pct for state in split_states]),
        }
    return output


def concentration(states: list[LeverageState], split: str) -> dict[str, Any]:
    split_states = [state for state in states if state.split == split]
    months = Counter(state.timestamp_utc[:7] for state in split_states)
    symbols = Counter(state.symbol for state in split_states)
    return {
        "events": len(split_states),
        "top_month_share": round(max(months.values()) / len(split_states), 6) if split_states else 0.0,
        "top_symbol_share": round(max(symbols.values()) / len(split_states), 6) if split_states else 0.0,
        "events_by_month": dict(sorted(months.items())),
        "events_by_symbol": dict(sorted(symbols.items())),
    }


def verdict(summary: dict[str, Any], formation_concentration: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    formation = summary["formation"]
    if int(formation["events"]) < 20:
        reasons.append(f"formation leverage states {formation['events']} < 20")
    if float(formation["abs_fwd_3d"]["mean_pct"]) <= 2.0:
        reasons.append(f"formation 3d abs move {formation['abs_fwd_3d']['mean_pct']:.6f}% <= 2%")
    if float(formation_concentration["top_month_share"]) > 0.25:
        reasons.append(f"formation top month share {formation_concentration['top_month_share']:.2%} > 25%")
    if float(formation_concentration["top_symbol_share"]) > 0.35:
        reasons.append(f"formation top symbol share {formation_concentration['top_symbol_share']:.2%} > 35%")
    return {
        "status": "meta_observation_only" if not reasons else "meta_observation_rejected_as_hard_filter",
        "eligible_for_strategy": False,
        "eligible_as_hard_filter": False,
        "reasons": reasons,
    }


def run_audit(
    data_dir: Path,
    symbols: list[str],
    formation_end: str,
    oos_end: str,
) -> dict[str, Any]:
    formation_end_ts = parse_timestamp_ms(f"{formation_end} 16:00:00")
    oos_end_ts = parse_timestamp_ms(f"{oos_end} 16:00:00")
    states: list[LeverageState] = []
    skipped: dict[str, str] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        oi_path = data_dir / f"{symbol}_open_interest_1d.csv"
        price_path = data_dir / f"{base}_15m.csv"
        if not oi_path.exists() or not price_path.exists():
            skipped[symbol] = "missing_oi_or_15m"
            continue
        oi_rows = load_oi(oi_path)
        bars = load_price_bars(price_path)
        if len(oi_rows) < LOOKBACK_DAYS + 10 or len(bars) < 96 * 30:
            skipped[symbol] = "insufficient_history"
            continue
        states.extend(generate_states_for_symbol(symbol, oi_rows, bars, formation_end_ts, oos_end_ts))

    summary = summarize_states(states)
    formation_concentration = concentration(states, "formation")
    oos_concentration = concentration(states, "oos")
    return {
        "research_id": "oi_deleveraging_filter",
        "scope": "meta_only_filter_research_not_strategy",
        "parameters": {
            "oivr": "daily open_interest_usd / trailing 24h close*volume notional proxy",
            "oi_available_at_utc": "16:00",
            "entry_time": "16:15 UTC 15m bar",
            "lookback_days": LOOKBACK_DAYS,
            "oivr_percentile": OIVR_PERCENTILE,
            "min_oi_7d_change": MIN_OI_7D_CHANGE,
            "forward_horizons_days": [1, 3, 7],
        },
        "formation_period": f"first eligible state to {formation_end}",
        "oos_period": f"after {formation_end} to {oos_end}",
        "symbols": symbols,
        "skipped_symbols": skipped,
        "summary": summary,
        "formation_concentration": formation_concentration,
        "oos_concentration": oos_concentration,
        "verdict": verdict(summary, formation_concentration),
        "event_preview": [asdict(state) for state in states[:30]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit daily OI deleveraging filter states.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+")
    parser.add_argument("--formation-end", default="2025-07-10")
    parser.add_argument("--oos-end", default="2026-06-10")
    parser.add_argument("--out", type=Path, default=Path("reports/oi_deleveraging_filter_audit.json"))
    args = parser.parse_args(argv)
    symbols = args.symbols or discover_symbols(args.data)
    report = run_audit(args.data, symbols, args.formation_end, args.oos_end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
