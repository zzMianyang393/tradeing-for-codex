"""BTC/ETH 1h incremental refresh for production-bound 1h research sleeves.

Public market data only. OKX bar parameter must be ``1H`` (not ``1h``).
Canonical local files: ``BTC_1h.csv`` / ``ETH_1h.csv``; also reads legacy
``*_1H.csv`` if present. Never places orders. Default dry-run; commit explicit.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from okx_downloader import fetch_page
from okx_incremental_15m_refresh import (
    completed_new_rows,
    utc,
    write_csv,
)
from market import _parse_timestamp
from prod.majors_contract import STRATEGY_ID, MajorsSleeveConfig
from prod.policy import PRODUCTION_BOUND_SYMBOLS

BAR_MS = 3_600_000
OKX_BAR = "1H"  # OKX API requires capital H for hourly
CANONICAL_SUFFIX = "1h"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def majors_symbols() -> list[str]:
    return list(MajorsSleeveConfig().symbols)


def path_for_1h(symbol: str, data_dir: Path) -> Path:
    """Prefer canonical lowercase 1h; fall back to OKX-style 1H if only that exists."""
    base = symbol.split("-", 1)[0]
    preferred = data_dir / f"{base}_{CANONICAL_SUFFIX}.csv"
    if preferred.exists():
        return preferred
    legacy = data_dir / f"{base}_1H.csv"
    if legacy.exists():
        return legacy
    return preferred


def ts_from_cell(value: str) -> int:
    """Accept quantify datetime strings or numeric ms/sec (market-compatible)."""
    return int(_parse_timestamp(str(value).strip()))


def read_1h_rows(path: Path) -> list[dict[str, str]]:
    """Read 1h CSV; normalize timestamp column to UTC string for append commits."""
    import csv

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"empty 1h CSV: {path}")
    fields = list(rows[0].keys())
    if "timestamp" not in fields or "open" not in fields:
        raise ValueError(f"unexpected 1h CSV schema: {path} fields={fields}")
    normalized: list[dict[str, str]] = []
    for row in rows:
        ts_ms = ts_from_cell(row["timestamp"])
        normalized.append(
            {
                "timestamp": utc(ts_ms),
                "open": str(row["open"]),
                "high": str(row["high"]),
                "low": str(row["low"]),
                "close": str(row["close"]),
                "volume": str(row.get("volume") or row.get("volume_quote") or "0"),
            }
        )
    # Drop pure-duplicate timestamps (keep first) after normalize
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for row in normalized:
        if row["timestamp"] in seen:
            continue
        seen.add(row["timestamp"])
        deduped.append(row)
    return deduped


def fetch_completed_pages_until(
    symbol: str,
    local_last_ts: int,
    *,
    fetch: Callable[..., list[list[str]]] = fetch_page,
    max_pages: int = 120,
) -> list[list[str]]:
    """Walk older OKX 1H pages until coverage reaches local_last_ts (or exhaust)."""
    collected: list[list[str]] = []
    after: int | None = None
    seen_oldest: int | None = None
    for _ in range(max_pages):
        page = fetch(symbol, OKX_BAR, after=after, limit=100)
        if not page:
            break
        collected.extend(page)
        oldest = min(int(row[0]) for row in page)
        if oldest <= local_last_ts:
            break
        if seen_oldest is not None and oldest >= seen_oldest:
            break
        seen_oldest = oldest
        after = oldest
    return collected


def plan_symbol_paginated(
    symbol: str,
    data_dir: Path,
    *,
    fetch: Callable[..., list[list[str]]] = fetch_page,
    max_pages: int = 120,
    allow_gap_fill_without_contiguity: bool = False,
) -> dict[str, Any]:
    path = path_for_1h(symbol, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"missing 1h CSV for {symbol}: {path}")
    existing = read_1h_rows(path)
    local_last_ts = ts_from_cell(existing[-1]["timestamp"])
    # Truncated/legacy numeric bars may not land on hour boundaries; snap plan
    # to last full hour so OKX contiguous append can attach cleanly.
    hour_aligned = local_last_ts - (local_last_ts % BAR_MS)
    if hour_aligned != local_last_ts:
        # Drop trailing partial/misaligned bar from the append base
        existing = [
            row for row in existing if ts_from_cell(row["timestamp"]) <= hour_aligned
        ]
        if not existing:
            raise ValueError(f"no hour-aligned rows in {path}")
        local_last_ts = ts_from_cell(existing[-1]["timestamp"])
        hour_aligned = local_last_ts - (local_last_ts % BAR_MS)
        if hour_aligned != local_last_ts:
            local_last_ts = hour_aligned
    remote = fetch_completed_pages_until(
        symbol, local_last_ts, fetch=fetch, max_pages=max_pages
    )
    new_rows = completed_new_rows(remote, local_last_ts)
    timestamps = [ts_from_cell(row["timestamp"]) for row in new_rows]
    contiguous = True
    gap_note = None
    if timestamps:
        if timestamps[0] != local_last_ts + BAR_MS:
            contiguous = False
            gap_note = (
                f"gap_or_missing_after_local:{utc(local_last_ts)}->"
                f"{utc(timestamps[0])}"
            )
        if any(right - left != BAR_MS for left, right in zip(timestamps, timestamps[1:])):
            contiguous = False
            gap_note = (gap_note or "") + ";internal_non_contiguous"
    if not contiguous and not allow_gap_fill_without_contiguity:
        raise ValueError(
            f"non-contiguous remote data for {symbol}: "
            f"{utc(local_last_ts)} -> "
            f"{utc(timestamps[0]) if timestamps else 'no_new'}"
            + (f" ({gap_note})" if gap_note else "")
        )
    # Commit path always rewrites normalized existing + append (fixes legacy stamps)
    return {
        "symbol": symbol,
        "path": str(path),
        "existing_rows": len(existing),
        "existing_for_commit": existing,
        "local_last_utc": utc(local_last_ts),
        "append_rows": new_rows,
        "append_count": len(new_rows),
        "new_last_utc": new_rows[-1]["timestamp"] if new_rows else utc(local_last_ts),
        "contiguous": contiguous,
        "gap_note": gap_note,
        "okx_bar": OKX_BAR,
        "bar_ms": BAR_MS,
        "rewrite_normalized": True,
        "pages_fetched_estimate": True,
    }


def commit_1h_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Commit with normalized existing rows (not re-read raw legacy timestamps)."""
    import os
    from pathlib import Path as P

    if not plan["all_contiguous"]:
        raise ValueError("cannot commit an invalid plan")
    changed = [
        item
        for item in plan["symbols"]
        if item["append_count"] or item.get("rewrite_normalized")
    ]
    # Always rewrite when rewrite_normalized so legacy stamps become strings
    if not any(item["append_count"] for item in plan["symbols"]):
        # still rewrite normalize if requested and files dirty
        pass
    backups: dict[P, bytes] = {}
    temps: dict[P, P] = {}
    try:
        wrote = False
        for item in plan["symbols"]:
            path = P(item["path"])
            existing = item.get("existing_for_commit")
            if existing is None:
                existing = read_1h_rows(path)
            append_rows = item.get("append_rows") or []
            if not append_rows and not item.get("rewrite_normalized"):
                continue
            backups[path] = path.read_bytes()
            temps[path] = write_csv(path, existing, append_rows)
            wrote = True
        for path, temp in temps.items():
            os.replace(temp, path)
        if wrote and any(item["append_count"] for item in plan["symbols"]):
            plan["mode"], plan["committed"] = "commit", True
        elif wrote:
            plan["mode"], plan["committed"] = "commit_normalized_only", True
        else:
            plan["mode"], plan["committed"] = "commit_no_changes", False
        return plan
    except Exception:
        for path, content in backups.items():
            path.write_bytes(content)
        raise
    finally:
        for temp in temps.values():
            if temp.exists():
                temp.unlink()


def build_majors_1h_refresh_plan(
    data_dir: Path,
    *,
    fetch: Callable[..., list[list[str]]] | None = None,
    max_pages: int = 120,
) -> dict[str, Any]:
    fetch_fn = fetch or fetch_page
    symbols = majors_symbols()
    for sym in symbols:
        if sym not in PRODUCTION_BOUND_SYMBOLS:
            raise ValueError(f"non_production_bound_symbol:{sym}")
    items = [
        plan_symbol_paginated(sym, data_dir, fetch=fetch_fn, max_pages=max_pages)
        for sym in symbols
    ]
    return {
        "report_type": "okx_incremental_1h_refresh",
        "mode": "dry_run",
        "observation_only": True,
        "okx_bar": OKX_BAR,
        "symbols": items,
        "symbol_count": len(items),
        "total_append_count": sum(item["append_count"] for item in items),
        "all_contiguous": all(item.get("contiguous", True) for item in items),
        "committed": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def run_majors_1h_refresh(
    data_dir: Path,
    *,
    commit: bool = False,
    workers: int = 1,
    fetch: Callable[..., list] | None = None,
    max_pages: int = 120,
) -> dict[str, Any]:
    """Plan (and optionally commit) incremental 1h append for BTC+ETH only."""
    _ = workers
    try:
        plan = build_majors_1h_refresh_plan(
            data_dir, fetch=fetch, max_pages=max_pages
        )
    except Exception as exc:  # network / schema / missing files
        return {
            "report_type": "majors_1h_refresh",
            "as_of": _utc_now(),
            "formal_status": "fail",
            "strategy_id": STRATEGY_ID,
            "symbols": majors_symbols(),
            "error": str(exc),
            "committed": False,
            "places_exchange_orders": False,
            "live_allowed": False,
            "okx_bar": OKX_BAR,
            "notes": "1h refresh failed before commit. No CSVs modified.",
        }

    committed = False
    mode = plan.get("mode")
    if commit:
        plan = commit_1h_plan(plan)
        committed = bool(plan.get("committed"))
        mode = plan.get("mode")

    formal = "ok"
    if plan.get("total_append_count", 0) > 0 and not commit:
        formal = "dry_run_pending_commit"
    elif commit and plan.get("total_append_count", 0) > 0 and not committed:
        formal = "fail"

    compact_symbols = []
    for item in plan.get("symbols") or []:
        compact_symbols.append(
            {
                "symbol": item.get("symbol"),
                "path": item.get("path"),
                "existing_rows": item.get("existing_rows"),
                "local_last_utc": item.get("local_last_utc"),
                "append_count": item.get("append_count"),
                "new_last_utc": item.get("new_last_utc"),
                "contiguous": item.get("contiguous"),
            }
        )

    return {
        "report_type": "majors_1h_refresh",
        "as_of": _utc_now(),
        "formal_status": formal,
        "strategy_id": STRATEGY_ID,
        "mode": mode,
        "committed": committed,
        "total_append_count": plan.get("total_append_count", 0),
        "all_contiguous": plan.get("all_contiguous"),
        "symbols": compact_symbols,
        "places_exchange_orders": False,
        "live_allowed": False,
        "ready_for_demo": False,
        "okx_bar": OKX_BAR,
        "notes": (
            "Public OKX 1H paginated incremental refresh for BTC/ETH only. "
            "Default dry-run; pass commit=True to write CSVs. No trading."
        ),
    }


def write_majors_1h_refresh_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
