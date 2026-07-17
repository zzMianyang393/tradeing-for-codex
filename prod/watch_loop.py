"""Finite watch loop: refresh + paper cycle under a single runtime lock."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import time
from pathlib import Path
from typing import Any, Callable

from prod.runtime_lock import DEFAULT_LOCK_PATH, RuntimeLock
from prod.ten_u_market_refresh import run_ten_u_market_refresh
from prod.ten_u_paper_runtime import (
    DEFAULT_CYCLE_PATH,
    DEFAULT_STATE_PATH,
    run_paper_cycle,
)
from prod.registry import DEFAULT_REGISTRY_PATH


RefreshFn = Callable[..., dict[str, Any]]
CycleFn = Callable[..., dict[str, Any]]


def run_locked_pipeline(
    *,
    data_dir: Path,
    manifest_path: Path,
    state_path: Path = DEFAULT_STATE_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cycle_path: Path = DEFAULT_CYCLE_PATH,
    lock_path: Path = DEFAULT_LOCK_PATH,
    lookback_days: int = 120,
    force: bool = False,
    refresh_fn: RefreshFn = run_ten_u_market_refresh,
    cycle_fn: CycleFn = run_paper_cycle,
    lock_timeout_seconds: float = 0.0,
) -> dict[str, Any]:
    with RuntimeLock(lock_path) as lock:
        # touch lock so acquire already held
        _ = lock
        refresh_report = refresh_fn(data_dir, manifest_path)
        cycle_report = cycle_fn(
            data_dir=data_dir,
            manifest_path=manifest_path,
            state_path=state_path,
            registry_path=registry_path,
            cycle_path=cycle_path,
            lookback_days=lookback_days,
            force=force,
        )
        return {
            "report_type": "ten_u_locked_pipeline",
            "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "lock_path": str(lock_path),
            "formal_status": cycle_report.get("formal_status"),
            "refresh_status": refresh_report.get("formal_status"),
            "refresh_errors": refresh_report.get("errors") or [],
            "paper_cycle": cycle_report,
            "available_through": refresh_report.get("available_through"),
        }


def run_watch_loop(
    *,
    iterations: int,
    interval_seconds: float,
    data_dir: Path,
    manifest_path: Path,
    state_path: Path = DEFAULT_STATE_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cycle_path: Path = DEFAULT_CYCLE_PATH,
    lock_path: Path = DEFAULT_LOCK_PATH,
    lookback_days: int = 120,
    force: bool = False,
    report_path: Path = Path("reports/prod/ten_u_watch_loop.json"),
    sleep_fn: Callable[[float], None] = time.sleep,
    pipeline_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    results: list[dict[str, Any]] = []
    runner = pipeline_fn or (
        lambda: run_locked_pipeline(
            data_dir=data_dir,
            manifest_path=manifest_path,
            state_path=state_path,
            registry_path=registry_path,
            cycle_path=cycle_path,
            lock_path=lock_path,
            lookback_days=lookback_days,
            force=force,
        )
    )
    for index in range(iterations):
        try:
            item = runner()
            item["iteration"] = index + 1
            results.append(item)
        except TimeoutError as exc:
            results.append(
                {
                    "iteration": index + 1,
                    "formal_status": "lock_busy",
                    "error": str(exc),
                    "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "iteration": index + 1,
                    "formal_status": "fail",
                    "error": str(exc),
                    "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            )
        if index + 1 < iterations and interval_seconds > 0:
            sleep_fn(interval_seconds)

    statuses = [r.get("formal_status") for r in results]
    if all(s == "ok" for s in statuses):
        formal = "ok"
    elif any(s == "ok" for s in statuses):
        formal = "partial"
    else:
        formal = statuses[-1] if statuses else "fail"

    report = {
        "report_type": "ten_u_watch_loop",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "iterations_requested": iterations,
        "interval_seconds": interval_seconds,
        "formal_status": formal,
        "cycles": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
