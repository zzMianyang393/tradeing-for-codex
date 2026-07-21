"""Safely append completed public OKX 15m candles to the local research CSVs."""
from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from okx_downloader import fetch_page
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS

BAR_MS = 900_000
HEADER = ["timestamp", "open", "high", "low", "close", "volume"]


def ts_from_text(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def path_for(symbol: str, data_dir: Path) -> Path:
    return data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or list(rows[0]) != HEADER:
        raise ValueError(f"unexpected 15m CSV schema: {path}")
    return rows


def completed_new_rows(remote: list[list[str]], local_last_ts: int) -> list[dict[str, str]]:
    rows = []
    for item in remote:
        if len(item) < 9 or item[8] != "1":
            continue
        ts = int(item[0])
        if ts > local_last_ts:
            rows.append({"timestamp": utc(ts), "open": item[1], "high": item[2], "low": item[3], "close": item[4], "volume": item[6]})
    rows.sort(key=lambda row: ts_from_text(row["timestamp"]))
    return rows


def plan_symbol(symbol: str, data_dir: Path, fetch: Callable[..., list[list[str]]] = fetch_page) -> dict[str, Any]:
    path = path_for(symbol, data_dir)
    existing = read_rows(path)
    local_last_ts = ts_from_text(existing[-1]["timestamp"])
    new_rows = completed_new_rows(fetch(symbol, "15m", limit=100), local_last_ts)
    timestamps = [ts_from_text(row["timestamp"]) for row in new_rows]
    if timestamps and timestamps[0] != local_last_ts + BAR_MS:
        raise ValueError(f"non-contiguous remote data for {symbol}: {utc(local_last_ts)} -> {utc(timestamps[0])}")
    if any(right - left != BAR_MS for left, right in zip(timestamps, timestamps[1:])):
        raise ValueError(f"non-contiguous appended candles for {symbol}")
    return {"symbol": symbol, "path": str(path), "existing_rows": len(existing), "local_last_utc": utc(local_last_ts),
            "append_rows": new_rows, "append_count": len(new_rows), "new_last_utc": new_rows[-1]["timestamp"] if new_rows else utc(local_last_ts)}


def build_plan(
    data_dir: Path,
    symbols: list[str],
    fetch: Callable[..., list[list[str]]] = fetch_page,
    workers: int = 1,
) -> dict[str, Any]:
    """Build a read-only append plan, preserving input symbol order.

    Parallelism is bounded and applies only to independent public API reads.
    CSV changes remain a separate, transactional sequential commit step.
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if workers == 1:
        items = [plan_symbol(symbol, data_dir, fetch) for symbol in symbols]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            planned = list(pool.map(lambda symbol: plan_symbol(symbol, data_dir, fetch), symbols))
        items = planned
    return {"report_type": "okx_incremental_15m_refresh", "mode": "dry_run", "observation_only": True,
            "symbols": items, "symbol_count": len(items), "total_append_count": sum(item["append_count"] for item in items),
            "all_contiguous": True, "committed": False,
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def write_csv(path: Path, existing: list[dict[str, str]], appended: list[dict[str, str]]) -> Path:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(existing)
        writer.writerows(appended)
    return Path(temp_name)


def commit_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not plan["all_contiguous"]:
        raise ValueError("cannot commit an invalid plan")
    changed = [item for item in plan["symbols"] if item["append_count"]]
    if not changed:
        plan["mode"], plan["committed"] = "commit_no_changes", False
        return plan
    backups: dict[Path, bytes] = {}
    temps: dict[Path, Path] = {}
    try:
        for item in changed:
            path = Path(item["path"])
            backups[path] = path.read_bytes()
            temps[path] = write_csv(path, read_rows(path), item["append_rows"])
        for path, temp in temps.items():
            os.replace(temp, path)
        plan["mode"], plan["committed"] = "commit", True
        return plan
    except Exception:
        for path, content in backups.items():
            path.write_bytes(content)
        raise
    finally:
        for temp in temps.values():
            if temp.exists():
                temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--workers", type=int, default=1, help="Bounded concurrent public API reads for dry-run planning.")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("reports/okx_incremental_15m_refresh.json"))
    args = parser.parse_args()
    report = build_plan(args.data, args.symbols, workers=args.workers)
    if args.commit:
        report = commit_plan(report)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"append={report['total_append_count']}; committed={report['committed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
