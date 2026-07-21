"""BTC/ETH 15m incremental refresh for production-bound majors sleeve.

Public market data only. Paginates OKX history until the local last bar
is covered (fixes stale multi-day gaps that a single 100-bar page misses).
Never places orders. Default dry-run; commit is explicit.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from okx_downloader import fetch_page
from okx_incremental_15m_refresh import (
    BAR_MS,
    commit_plan,
    completed_new_rows,
    path_for,
    read_rows,
    ts_from_text,
    utc,
)
from prod.majors_contract import MajorsSleeveConfig, STRATEGY_ID
from prod.policy import PRODUCTION_BOUND_SYMBOLS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def majors_symbols() -> list[str]:
    return list(MajorsSleeveConfig().symbols)


def fetch_completed_pages_until(
    symbol: str,
    local_last_ts: int,
    *,
    fetch: Callable[..., list[list[str]]] = fetch_page,
    max_pages: int = 80,
) -> list[list[str]]:
    """Walk older OKX pages until coverage reaches local_last_ts (or exhaust)."""
    collected: list[list[str]] = []
    after: int | None = None
    seen_oldest: int | None = None
    for _ in range(max_pages):
        page = fetch(symbol, "15m", after=after, limit=100)
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
    max_pages: int = 80,
    allow_gap_fill_without_contiguity: bool = False,
) -> dict[str, Any]:
    path = path_for(symbol, data_dir)
    existing = read_rows(path)
    local_last_ts = ts_from_text(existing[-1]["timestamp"])
    remote = fetch_completed_pages_until(
        symbol, local_last_ts, fetch=fetch, max_pages=max_pages
    )
    new_rows = completed_new_rows(remote, local_last_ts)
    timestamps = [ts_from_text(row["timestamp"]) for row in new_rows]
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
    return {
        "symbol": symbol,
        "path": str(path),
        "existing_rows": len(existing),
        "local_last_utc": utc(local_last_ts),
        "append_rows": new_rows,
        "append_count": len(new_rows),
        "new_last_utc": new_rows[-1]["timestamp"] if new_rows else utc(local_last_ts),
        "contiguous": contiguous,
        "gap_note": gap_note,
        "pages_fetched_estimate": True,
    }


def build_majors_refresh_plan(
    data_dir: Path,
    *,
    fetch: Callable[..., list[list[str]]] | None = None,
    max_pages: int = 80,
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
        "report_type": "okx_incremental_15m_refresh",
        "mode": "dry_run",
        "observation_only": True,
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


def run_majors_15m_refresh(
    data_dir: Path,
    *,
    commit: bool = False,
    workers: int = 1,
    fetch: Callable[..., list] | None = None,
    max_pages: int = 80,
) -> dict[str, Any]:
    """Plan (and optionally commit) incremental 15m append for BTC+ETH only."""
    _ = workers  # sequential paginated reads; workers reserved for API
    try:
        plan = build_majors_refresh_plan(
            data_dir, fetch=fetch, max_pages=max_pages
        )
    except Exception as exc:  # network / schema
        return {
            "report_type": "majors_15m_refresh",
            "as_of": _utc_now(),
            "formal_status": "fail",
            "strategy_id": STRATEGY_ID,
            "symbols": majors_symbols(),
            "error": str(exc),
            "committed": False,
            "places_exchange_orders": False,
            "live_allowed": False,
            "notes": "Refresh failed before commit. No CSVs modified.",
        }

    committed = False
    mode = plan.get("mode")
    if commit:
        plan = commit_plan(plan)
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
        "report_type": "majors_15m_refresh",
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
        "notes": (
            "Public OKX 15m paginated incremental refresh for BTC/ETH only. "
            "Default dry-run; pass commit=True to write CSVs. No trading."
        ),
    }


def write_majors_refresh_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
