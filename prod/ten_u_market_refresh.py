"""Production-track 10U market/funding refresh (no prospective ledger coupling)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable

from funding_rate import (
    FundingRate,
    fetch_funding_page,
    load_funding_rates,
    parse_funding_rows,
    save_funding_rates,
)
from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig
from ten_u_event_trend_data_v1 import (
    HOUR_MS,
    FullHourlyCandle,
    collect_completed_hourly,
    fetch_instrument,
    fetch_page,
    format_utc,
    load_hourly,
    validate_hourly,
    write_hourly,
)


FetchPage = Callable[[str, int | None, int], list[list[str]]]
FundingFetchPage = Callable[..., list[dict[str, Any]]]
InstrumentFetcher = Callable[[str], dict[str, Any]]


def floor_hour_ms(timestamp_ms: int) -> int:
    return timestamp_ms - (timestamp_ms % HOUR_MS)


def merge_hourly_candles(
    existing: list[FullHourlyCandle],
    additions: list[FullHourlyCandle],
) -> list[FullHourlyCandle]:
    """Merge by timestamp; refuse silent rewrites of OHLCV for known bars."""
    by_ts = {c.timestamp_ms: c for c in existing}
    for candle in additions:
        prior = by_ts.get(candle.timestamp_ms)
        if prior is not None:
            if (
                prior.open != candle.open
                or prior.high != candle.high
                or prior.low != candle.low
                or prior.close != candle.close
                or prior.volume_quote != candle.volume_quote
            ):
                raise ValueError(
                    f"refusing candle rewrite at {candle.timestamp_ms}"
                )
            continue
        by_ts[candle.timestamp_ms] = candle
    return [by_ts[k] for k in sorted(by_ts)]


def next_refresh_window(
    existing: list[FullHourlyCandle],
    *,
    now_ms: int,
    max_lookback_hours: int = 72,
) -> tuple[int, int]:
    """Return [start, end) of completed hours to fetch."""
    end_ms = floor_hour_ms(now_ms)
    if not existing:
        start_ms = end_ms - max_lookback_hours * HOUR_MS
        return start_ms, end_ms
    last = existing[-1].timestamp_ms
    start_ms = last + HOUR_MS
    if start_ms >= end_ms:
        return end_ms, end_ms  # empty window
    # Cap catch-up
    earliest = end_ms - max_lookback_hours * HOUR_MS
    if start_ms < earliest:
        start_ms = earliest
    return start_ms, end_ms


def merge_funding(
    existing: list[FundingRate],
    additions: list[FundingRate],
    symbol: str,
) -> list[FundingRate]:
    by_ts = {int(r.ts): r for r in existing}
    for rate in additions:
        ts = int(rate.ts)
        prior = by_ts.get(ts)
        if prior is not None:
            if float(prior.funding_rate) != float(rate.funding_rate):
                raise ValueError(f"refusing funding rewrite at {ts} for {symbol}")
            continue
        by_ts[ts] = rate
    ordered = [by_ts[k] for k in sorted(by_ts)]
    return ordered


def refresh_symbol_candles(
    symbol: str,
    candle_path: Path,
    *,
    now_ms: int,
    page_fetcher: FetchPage = fetch_page,
    max_lookback_hours: int = 72,
    sleep_seconds: float = 0.12,
) -> dict[str, Any]:
    existing = load_hourly(candle_path) if candle_path.exists() else []
    start_ms, end_ms = next_refresh_window(
        existing, now_ms=now_ms, max_lookback_hours=max_lookback_hours
    )
    if start_ms >= end_ms:
        validation = validate_hourly(existing)
        return {
            "symbol": symbol,
            "added_bars": 0,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "rows": len(existing),
            "validation": validation,
            "sha256": hashlib.sha256(candle_path.read_bytes()).hexdigest()
            if candle_path.exists()
            else None,
        }
    additions = collect_completed_hourly(
        symbol,
        start_ms,
        end_ms,
        page_fetcher=page_fetcher,
        sleep_seconds=sleep_seconds,
    )
    merged = merge_hourly_candles(existing, additions)
    validation = validate_hourly(merged)
    if validation["status"] != "PASS":
        raise ValueError(f"hourly validation failed for {symbol}: {validation}")
    digest = write_hourly(candle_path, merged)
    return {
        "symbol": symbol,
        "added_bars": len(additions),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "rows": len(merged),
        "first": merged[0].timestamp_utc if merged else None,
        "last": merged[-1].timestamp_utc if merged else None,
        "validation": validation,
        "sha256": digest,
    }


def refresh_symbol_funding(
    symbol: str,
    funding_path: Path,
    *,
    available_through_ms: int,
    page_fetcher: FundingFetchPage = fetch_funding_page,
    sleep_seconds: float = 0.12,
) -> dict[str, Any]:
    existing = load_funding_rates(funding_path) if funding_path.exists() else []
    after_ts = int(existing[-1].ts) if existing else None
    # Paginate newest-first using `before` (same pattern as download_funding_rates).
    collected: list[FundingRate] = []
    cursor: int | None = None
    previous_oldest: int | None = None
    for _ in range(20):
        page = page_fetcher(symbol, before=cursor, limit=100)
        if not page:
            break
        parsed = parse_funding_rows(page)
        if not parsed:
            break
        for rate in parsed:
            if int(rate.ts) <= available_through_ms:
                if after_ts is None or int(rate.ts) > after_ts:
                    collected.append(rate)
        oldest = min(int(r.ts) for r in parsed)
        if after_ts is not None and oldest <= after_ts:
            break
        if previous_oldest is not None and oldest >= previous_oldest:
            break
        previous_oldest = oldest
        cursor = oldest
        if sleep_seconds:
            time.sleep(sleep_seconds)
    merged = merge_funding(existing, collected, symbol)
    save_funding_rates(funding_path, merged)
    digest = hashlib.sha256(funding_path.read_bytes()).hexdigest()
    return {
        "symbol": symbol,
        "added_points": len({int(r.ts) for r in collected}),
        "rows": len(merged),
        "sha256": digest,
        "first": format_utc(int(merged[0].ts)) if merged else None,
        "last": format_utc(int(merged[-1].ts)) if merged else None,
    }


def update_manifest_hashes(
    manifest_path: Path,
    candle_results: dict[str, dict[str, Any]],
    funding_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for symbol, c_res in candle_results.items():
        item = manifest["symbols"][symbol]
        if c_res.get("sha256"):
            item["sha256"] = c_res["sha256"]
        if c_res.get("validation"):
            item["validation"] = {
                **item.get("validation", {}),
                **{
                    k: c_res["validation"].get(k)
                    for k in (
                        "status",
                        "rows",
                        "first_timestamp",
                        "last_timestamp",
                        "missing_hours",
                        "reasons",
                    )
                    if k in c_res["validation"]
                },
            }
            # normalize field names from validate_hourly
            val = c_res["validation"]
            item["validation"]["first_timestamp"] = val.get("first_timestamp")
            item["validation"]["last_timestamp"] = val.get("last_timestamp")
            item["validation"]["rows"] = val.get("rows")
            item["validation"]["status"] = val.get("status")
        f_res = funding_results.get(symbol) or {}
        if "funding" not in item:
            item["funding"] = {}
        if f_res.get("sha256"):
            item["funding"]["sha256"] = f_res["sha256"]
            item["funding"]["path"] = item["funding"].get(
                "path", f"data/event_trend_v1/{symbol}_funding.csv"
            )
        if f_res.get("rows") is not None:
            item["funding"].setdefault("validation", {})
            item["funding"]["validation"]["rows"] = f_res["rows"]
            item["funding"]["validation"]["status"] = "PASS"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def run_ten_u_market_refresh(
    data_dir: Path,
    manifest_path: Path,
    *,
    now_ms: int | None = None,
    page_fetcher: FetchPage = fetch_page,
    funding_page_fetcher: FundingFetchPage = fetch_funding_page,
    instrument_fetcher: InstrumentFetcher = fetch_instrument,
    sleep_seconds: float = 0.12,
) -> dict[str, Any]:
    config = PersistentEventTrendConfig()
    now = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    candle_results: dict[str, dict[str, Any]] = {}
    funding_results: dict[str, dict[str, Any]] = {}
    instruments: dict[str, Any] = {}
    errors: list[str] = []

    for symbol in config.symbols:
        try:
            instruments[symbol] = instrument_fetcher(symbol)
        except Exception as exc:
            errors.append(f"instrument:{symbol}:{exc}")
            instruments[symbol] = {"error": str(exc)}

    manifest_blob = json.loads(manifest_path.read_text(encoding="utf-8"))

    for symbol in config.symbols:
        item = manifest_blob["symbols"][symbol]
        raw_path = Path(item["path"])
        if raw_path.is_absolute() and raw_path.exists():
            candle_path = raw_path
        elif raw_path.exists():
            candle_path = raw_path
        elif (data_dir / raw_path.name).exists():
            candle_path = data_dir / raw_path.name
        else:
            candle_path = data_dir / raw_path.name
        funding_path = data_dir / f"{symbol}_funding.csv"
        try:
            candle_results[symbol] = refresh_symbol_candles(
                symbol,
                candle_path,
                now_ms=now,
                page_fetcher=page_fetcher,
                sleep_seconds=sleep_seconds,
            )
        except Exception as exc:
            errors.append(f"candles:{symbol}:{exc}")
            candle_results[symbol] = {"symbol": symbol, "error": str(exc)}
        try:
            end_ms = floor_hour_ms(now)
            funding_results[symbol] = refresh_symbol_funding(
                symbol,
                funding_path,
                available_through_ms=end_ms,
                page_fetcher=funding_page_fetcher,
                sleep_seconds=sleep_seconds,
            )
        except Exception as exc:
            errors.append(f"funding:{symbol}:{exc}")
            funding_results[symbol] = {"symbol": symbol, "error": str(exc)}

    try:
        # Re-resolve candle paths into manifest using absolute-ish relative paths
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for symbol in config.symbols:
            c_res = candle_results.get(symbol) or {}
            if c_res.get("sha256") and "error" not in c_res:
                manifest["symbols"][symbol]["sha256"] = c_res["sha256"]
                val = c_res.get("validation") or {}
                if val:
                    manifest["symbols"][symbol]["validation"] = {
                        "status": val.get("status"),
                        "rows": val.get("rows"),
                        "first_timestamp": val.get("first_timestamp"),
                        "last_timestamp": val.get("last_timestamp"),
                        "missing_hours": val.get("missing_hours") or [],
                        "reasons": val.get("reasons") or [],
                    }
            f_res = funding_results.get(symbol) or {}
            if f_res.get("sha256") and "error" not in f_res:
                funding_meta = manifest["symbols"][symbol].setdefault("funding", {})
                funding_meta["sha256"] = f_res["sha256"]
                funding_meta["path"] = str(
                    (data_dir / f"{symbol}_funding.csv").as_posix()
                )
                funding_meta.setdefault("validation", {})
                funding_meta["validation"]["rows"] = f_res.get("rows")
                funding_meta["validation"]["status"] = "PASS"
        manifest["requested_end"] = format_utc(floor_hour_ms(now))
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except Exception as exc:
        errors.append(f"manifest:{exc}")

    status = "ok" if not errors else "partial"
    return {
        "report_type": "ten_u_market_refresh",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "formal_status": status,
        "now_ms": now,
        "available_through": format_utc(floor_hour_ms(now)),
        "candles": candle_results,
        "funding": funding_results,
        "instruments": instruments,
        "errors": errors,
    }
