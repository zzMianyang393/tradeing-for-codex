"""Locked local paper pipeline for production-bound majors (BTC/ETH).

No exchange orders. Optional data preflight only (local files); network
refresh is not required for a cycle when CSVs already exist.

Supports default 15m donchian sleeve and admitted 1h research sleeves
(via strategy_id + timeframe-aware refresh/preflight).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from market import quantify_bar_path
from prod.majors_contract import (
    MajorsSleeveConfig,
    STRATEGY_ID,
    resolve_sleeve_config,
)
from prod.majors_paper_runtime import (
    DEFAULT_CYCLE_PATH,
    DEFAULT_STATE_PATH,
    run_majors_paper_cycle,
)
from prod.majors_refresh import run_majors_15m_refresh
from prod.majors_refresh_1h import run_majors_1h_refresh
from prod.registry import DEFAULT_REGISTRY_PATH
from prod.runtime_lock import RuntimeLock


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timeframe_file_suffix(timeframe_minutes: int) -> str:
    return {
        5: "5m",
        15: "15m",
        60: "1h",
        240: "4h",
        1440: "1d",
    }.get(int(timeframe_minutes), f"{int(timeframe_minutes)}m")


def resolve_pipeline_config(
    strategy_id: str | None = None,
    config: MajorsSleeveConfig | None = None,
) -> MajorsSleeveConfig:
    if config is not None:
        return config
    sid = strategy_id or STRATEGY_ID
    return resolve_sleeve_config(sid) or MajorsSleeveConfig()


def majors_data_preflight(
    data_dir: Path,
    *,
    config: MajorsSleeveConfig | None = None,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    """Check local OHLCV CSVs for BTC/ETH without network I/O."""
    cfg = resolve_pipeline_config(strategy_id=strategy_id, config=config)
    symbols_status: dict[str, Any] = {}
    errors: list[str] = []
    tf = timeframe_file_suffix(cfg.timeframe_minutes)
    for sym in cfg.symbols:
        base = sym.removesuffix("-USDT-SWAP")
        path = quantify_bar_path(data_dir, base, tf)
        if path is None:
            expected = data_dir / f"{base}_{tf}.csv"
            errors.append(f"missing:{expected.name}")
            symbols_status[sym] = {"exists": False, "path": str(expected)}
            continue
        try:
            text_tail = path.read_bytes()[-4096:].decode("utf-8", errors="ignore")
            last_line = [ln for ln in text_tail.splitlines() if ln.strip()][-1]
            symbols_status[sym] = {
                "exists": True,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "last_line_sample": last_line[:120],
            }
        except Exception as exc:  # noqa: BLE001 — preflight must not raise
            errors.append(f"unreadable:{path.name}:{exc}")
            symbols_status[sym] = {"exists": True, "path": str(path), "error": str(exc)}

    formal = "ok" if not errors else "data_missing"
    return {
        "report_type": "majors_data_preflight",
        "as_of": _utc_now(),
        "formal_status": formal,
        "strategy_id": cfg.strategy_id,
        "timeframe_minutes": cfg.timeframe_minutes,
        "timeframe_suffix": tf,
        "symbols": symbols_status,
        "errors": errors,
        "places_exchange_orders": False,
    }


CycleFn = Callable[..., dict[str, Any]]
PreflightFn = Callable[..., dict[str, Any]]


def default_refresh_fn_for_config(
    config: MajorsSleeveConfig,
) -> Callable[..., dict[str, Any]]:
    if int(config.timeframe_minutes) == 60:
        return run_majors_1h_refresh
    return run_majors_15m_refresh


def run_majors_locked_pipeline(
    *,
    data_dir: Path,
    state_path: Path = DEFAULT_STATE_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cycle_path: Path = DEFAULT_CYCLE_PATH,
    lock_path: Path = Path("reports/prod/majors_runtime.lock"),
    force: bool = False,
    skip_preflight: bool = False,
    strategy_id: str | None = None,
    config: MajorsSleeveConfig | None = None,
    funding_filter: str = "none",
    preflight_fn: PreflightFn | None = None,
    cycle_fn: CycleFn = run_majors_paper_cycle,
) -> dict[str, Any]:
    cfg = resolve_pipeline_config(strategy_id=strategy_id, config=config)
    sid = cfg.strategy_id
    preflight_impl = preflight_fn or (
        lambda d: majors_data_preflight(d, config=cfg, strategy_id=sid)
    )
    with RuntimeLock(lock_path) as _lock:
        _ = _lock
        if skip_preflight:
            preflight = {
                "report_type": "majors_data_preflight",
                "formal_status": "skipped",
                "errors": [],
                "strategy_id": sid,
            }
        else:
            preflight = preflight_impl(data_dir)
        if preflight.get("formal_status") == "data_missing":
            return {
                "report_type": "majors_locked_pipeline",
                "as_of": _utc_now(),
                "lock_path": str(lock_path),
                "formal_status": "data_missing",
                "strategy_id": sid,
                "preflight": preflight,
                "paper_cycle": None,
                "places_exchange_orders": False,
                "live_allowed": False,
            }
        cycle_report = cycle_fn(
            data_dir=data_dir,
            state_path=state_path,
            registry_path=registry_path,
            cycle_path=cycle_path,
            force=force,
            config=cfg,
            strategy_id=sid,
            funding_filter=funding_filter,
        )
        return {
            "report_type": "majors_locked_pipeline",
            "as_of": _utc_now(),
            "lock_path": str(lock_path),
            "formal_status": cycle_report.get("formal_status"),
            "strategy_id": sid,
            "preflight": preflight,
            "paper_cycle": cycle_report,
            "places_exchange_orders": False,
            "live_allowed": False,
        }


def run_majors_refresh_then_paper(
    *,
    data_dir: Path,
    state_path: Path = DEFAULT_STATE_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cycle_path: Path = DEFAULT_CYCLE_PATH,
    lock_path: Path = Path("reports/prod/majors_runtime.lock"),
    force: bool = False,
    skip_preflight: bool = False,
    refresh_data: bool = True,
    commit_refresh: bool = True,
    strategy_id: str | None = None,
    config: MajorsSleeveConfig | None = None,
    funding_filter: str = "none",
    refresh_fn: Callable[..., dict[str, Any]] | None = None,
    cycle_pipeline_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One scheduled unit: optional public refresh then locked local paper.

    Timeframe follows strategy config (15m default; 1h for admitted research sleeves).
    Never places exchange orders.
    """
    cfg = resolve_pipeline_config(strategy_id=strategy_id, config=config)
    sid = cfg.strategy_id
    refresh_impl = refresh_fn or default_refresh_fn_for_config(cfg)

    refresh_report: dict[str, Any] | None = None
    if refresh_data:
        refresh_report = refresh_impl(data_dir, commit=commit_refresh, workers=1)
        if commit_refresh and refresh_report.get("formal_status") == "fail":
            return {
                "report_type": "majors_hourly_job",
                "as_of": _utc_now(),
                "formal_status": "refresh_fail",
                "strategy_id": sid,
                "timeframe_minutes": cfg.timeframe_minutes,
                "data_refresh": refresh_report,
                "paper_pipeline": None,
                "places_exchange_orders": False,
                "live_allowed": False,
            }

    runner = cycle_pipeline_fn or (
        lambda: run_majors_locked_pipeline(
            data_dir=data_dir,
            state_path=state_path,
            registry_path=registry_path,
            cycle_path=cycle_path,
            lock_path=lock_path,
            force=force,
            skip_preflight=skip_preflight,
            strategy_id=sid,
            config=cfg,
            funding_filter=funding_filter,
        )
    )
    pipeline = runner()
    if refresh_report is not None:
        pipeline = dict(pipeline)
        pipeline["data_refresh"] = refresh_report

    formal = pipeline.get("formal_status")
    if refresh_report and refresh_report.get("formal_status") == "fail" and not commit_refresh:
        formal = pipeline.get("formal_status")

    return {
        "report_type": "majors_hourly_job",
        "as_of": _utc_now(),
        "formal_status": formal,
        "strategy_id": sid,
        "timeframe_minutes": cfg.timeframe_minutes,
        "data_refresh": refresh_report,
        "paper_pipeline": pipeline,
        "places_exchange_orders": False,
        "live_allowed": False,
        "track_class": "production_bound",
        "notes": (
            "Scheduled local job: refresh public bars for sleeve timeframe "
            f"({timeframe_file_suffix(cfg.timeframe_minutes)}) then paper cycle. "
            "No OKX demo/live orders."
        ),
    }


def run_majors_watch_loop(
    *,
    iterations: int,
    interval_seconds: float = 0.0,
    data_dir: Path = Path("data"),
    state_path: Path = DEFAULT_STATE_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cycle_path: Path = DEFAULT_CYCLE_PATH,
    lock_path: Path = Path("reports/prod/majors_runtime.lock"),
    force: bool = False,
    skip_preflight: bool = False,
    refresh_data: bool = False,
    commit_refresh: bool = False,
    strategy_id: str | None = None,
    config: MajorsSleeveConfig | None = None,
    funding_filter: str = "none",
    report_path: Path = Path("reports/prod/majors_watch_loop.json"),
    sleep_fn: Callable[[float], None] | None = None,
    pipeline_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    import time

    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    cfg = resolve_pipeline_config(strategy_id=strategy_id, config=config)
    sid = cfg.strategy_id
    sleeper = sleep_fn or time.sleep
    results: list[dict[str, Any]] = []
    runner = pipeline_fn or (
        lambda: run_majors_refresh_then_paper(
            data_dir=data_dir,
            state_path=state_path,
            registry_path=registry_path,
            cycle_path=cycle_path,
            lock_path=lock_path,
            force=force,
            skip_preflight=skip_preflight,
            refresh_data=refresh_data,
            commit_refresh=commit_refresh,
            strategy_id=sid,
            config=cfg,
            funding_filter=funding_filter,
        )
        if refresh_data
        else run_majors_locked_pipeline(
            data_dir=data_dir,
            state_path=state_path,
            registry_path=registry_path,
            cycle_path=cycle_path,
            lock_path=lock_path,
            force=force,
            skip_preflight=skip_preflight,
            strategy_id=sid,
            config=cfg,
            funding_filter=funding_filter,
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
                    "report_type": "majors_watch_iteration",
                    "formal_status": "lock_busy",
                    "error": str(exc),
                    "places_exchange_orders": False,
                    "live_allowed": False,
                    "strategy_id": sid,
                }
            )
        if index + 1 < iterations and interval_seconds > 0:
            sleeper(interval_seconds)

    ok = all(r.get("formal_status") == "ok" for r in results)
    partial = any(r.get("formal_status") == "ok" for r in results)
    formal = "ok" if ok else ("partial" if partial else "fail")
    report = {
        "report_type": "majors_watch_loop",
        "as_of": _utc_now(),
        "formal_status": formal,
        "strategy_id": sid,
        "timeframe_minutes": cfg.timeframe_minutes,
        "iterations": iterations,
        "refresh_data": bool(refresh_data),
        "commit_refresh": bool(commit_refresh),
        "cycles": results,
        "places_exchange_orders": False,
        "live_allowed": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
