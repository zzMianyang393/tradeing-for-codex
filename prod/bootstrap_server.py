"""Cold-start a slim git checkout on a trading server.

Git does not ship data/ or reports/. Default mode is **majors** (BTC/ETH 15m):
- data/BTC_15m.csv + ETH_15m.csv (public OKX)
- paper-prep registry seed for production-bound majors
Optional --mode ten_u|both keeps legacy RAVE/LAB 10U local_experiment path.

Trading API keys are NEVER written here (server agent injects later).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Literal

from funding_rate import (
    fetch_funding_page,
    load_funding_rates,
    parse_funding_rows,
    save_funding_rates,
)
from prod.majors_contract import (
    STRATEGY_ID as MAJORS_STRATEGY_ID,
    MajorsSleeveConfig,
)
from prod.registry import (
    DEFAULT_REGISTRY_PATH,
    PaperPrepEntry,
    get_entry,
    upsert_entry,
)
from prod.server_handoff import write_server_handoff_contract
from prod.ten_u_market_refresh import floor_hour_ms, merge_funding
from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig, STRATEGY_ID
from ten_u_event_trend_data_v1 import (
    HOUR_MS,
    download_dataset,
    format_utc,
)

BootstrapMode = Literal["majors", "ten_u", "both"]


# Symbol listing-aligned research starts (UTC Z).
DEFAULT_STARTS: dict[str, str] = {
    "RAVE-USDT-SWAP": "2025-12-15T08:00:00Z",
    "LAB-USDT-SWAP": "2025-11-01T12:00:00Z",
    "ETH-USDT-SWAP": "2025-11-01T00:00:00Z",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _end_iso_now() -> str:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return format_utc(floor_hour_ms(now_ms)).replace("+00:00", "Z")


def download_funding_history(
    symbol: str,
    path: Path,
    *,
    start_ms: int,
    end_ms: int,
    sleep_seconds: float = 0.12,
) -> dict[str, Any]:
    import time

    existing = load_funding_rates(path) if path.exists() else []
    collected = []
    cursor: int | None = None
    previous_oldest: int | None = None
    for _ in range(80):
        page = fetch_funding_page(symbol, before=cursor, limit=100)
        if not page:
            break
        parsed = parse_funding_rows(page)
        if not parsed:
            break
        for rate in parsed:
            ts = int(rate.ts)
            if start_ms <= ts <= end_ms:
                collected.append(rate)
        oldest = min(int(r.ts) for r in parsed)
        if oldest <= start_ms:
            break
        if previous_oldest is not None and oldest >= previous_oldest:
            break
        previous_oldest = oldest
        cursor = oldest
        if sleep_seconds:
            time.sleep(sleep_seconds)
    merged = merge_funding(existing, collected, symbol)
    save_funding_rates(path, merged)
    return {
        "symbol": symbol,
        "rows": len(merged),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "path": str(path).replace("\\", "/"),
    }


def seed_paper_registry(
    registry_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Legacy ten_u (RAVE/LAB) registry seed — local_experiment only."""
    config = PersistentEventTrendConfig()
    existing = get_entry(STRATEGY_ID, registry_path)
    if existing and existing.get("status") == "paper_prep" and not force:
        return {"action": "keep_existing", "entry": existing}
    entry = PaperPrepEntry(
        strategy_id=STRATEGY_ID,
        track="ten_u_high_risk",
        status="paper_prep",
        config_fingerprint=config.fingerprint(),
        admitted_at=_utc_now(),
        admission_decision="server_bootstrap_seed",
        warnings=[
            "seeded_on_server_without_local_backtest_report",
            "concentration_risk_accepted_for_high_risk_sleeve",
            "local_experiment_not_demo_live_graduation",
        ],
        live_allowed=False,
        notes=(
            "Seeded by prod.bootstrap_server for remote local paper ops. "
            "RAVE/LAB/ETH 10U sleeve is local_experiment — not demo/live graduation. "
            "Default pipeline places no exchange orders. "
            "Prospective wait not required. Live remains closed. "
            "Keys for any future demo/live are server-agent only."
        ),
        evidence_paths=["prod/bootstrap_server.py"],
    )
    upsert_entry(entry, registry_path)
    return {"action": "seeded", "entry": entry.to_dict()}


def seed_majors_registry(
    registry_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Production-bound BTC/ETH majors registry seed (default server path).

    Never overwrites suspended/rejected health decisions unless force=True.
    """
    config = MajorsSleeveConfig()
    existing = get_entry(MAJORS_STRATEGY_ID, registry_path)
    if existing and not force:
        status = existing.get("status")
        if status in {"paper_prep", "suspended", "rejected"}:
            return {"action": "keep_existing", "entry": existing}
    entry = PaperPrepEntry(
        strategy_id=MAJORS_STRATEGY_ID,
        track="production_bound_majors",
        status="paper_prep",
        config_fingerprint=config.fingerprint(),
        admitted_at=_utc_now(),
        admission_decision="server_bootstrap_seed_majors",
        warnings=[
            "seeded_on_server_without_full_readiness_package",
            "infrastructure_seed_not_alpha_approval",
        ],
        live_allowed=False,
        notes=(
            "Production-bound BTC/ETH majors local paper seed. "
            "No exchange orders from default pipeline. "
            "Demo/live only on server with agent-injected keys (later stage)."
        ),
        evidence_paths=["prod/bootstrap_server.py", "prod/majors_contract.py"],
    )
    upsert_entry(entry, registry_path)
    return {"action": "seeded", "entry": entry.to_dict()}


def ensure_majors_15m_data(
    data_dir: Path,
    *,
    skip_download: bool = False,
    days: int = 120,
) -> dict[str, Any]:
    """Ensure BTC/ETH 15m CSVs exist under data_dir (public download if missing)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    errors: list[str] = []
    for symbol in MajorsSleeveConfig().symbols:
        base = symbol.removesuffix("-USDT-SWAP")
        path = data_dir / f"{base}_15m.csv"
        if path.exists() and path.stat().st_size > 200:
            results[symbol] = {
                "action": "exists",
                "path": str(path).replace("\\", "/"),
                "size_bytes": path.stat().st_size,
            }
            continue
        if skip_download:
            results[symbol] = {
                "action": "missing",
                "path": str(path).replace("\\", "/"),
            }
            errors.append(f"missing:{path.name}")
            continue
        try:
            from okx_downloader import download_symbol

            rows = download_symbol(symbol, days=days, out_dir=data_dir, bar="15m")
            results[symbol] = {
                "action": "downloaded",
                "path": str(path).replace("\\", "/"),
                "rows": rows,
            }
        except Exception as exc:  # network
            errors.append(f"download:{symbol}:{exc}")
            results[symbol] = {"action": "download_failed", "error": str(exc)}
    formal = "ok" if not errors else ("partial" if results else "fail")
    return {
        "formal_status": formal,
        "symbols": results,
        "errors": errors,
        "places_exchange_orders": False,
    }


def _bootstrap_ten_u(
    *,
    data_dir: Path,
    registry_path: Path,
    start_overrides: dict[str, str] | None,
    skip_download: bool,
    seed_registry: bool,
    force_registry: bool,
) -> dict[str, Any]:
    config = PersistentEventTrendConfig()
    data_dir.mkdir(parents=True, exist_ok=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    end = _end_iso_now()
    starts = {**DEFAULT_STARTS, **(start_overrides or {})}
    global_start = min(starts[s] for s in config.symbols)
    errors: list[str] = []
    candle_manifest: dict[str, Any] | None = None
    funding: dict[str, Any] = {}

    if not skip_download:
        try:
            candle_manifest = download_dataset(
                list(config.symbols),
                global_start,
                end,
                data_dir,
            )
        except Exception as exc:
            errors.append(f"candles:{exc}")
            candle_manifest = None

        end_ms = floor_hour_ms(int(datetime.now(timezone.utc).timestamp() * 1000))
        for symbol in config.symbols:
            try:
                from ten_u_event_trend_data_v1 import parse_utc

                start_ms = parse_utc(starts[symbol])
                fpath = data_dir / f"{symbol}_funding.csv"
                funding[symbol] = download_funding_history(
                    symbol, fpath, start_ms=start_ms, end_ms=end_ms
                )
            except Exception as exc:
                errors.append(f"funding:{symbol}:{exc}")
                funding[symbol] = {"error": str(exc)}

        manifest_path = data_dir / "hourly_dataset_manifest_v1.json"
        if manifest_path.exists() and candle_manifest is not None:
            try:
                man = json.loads(manifest_path.read_text(encoding="utf-8"))
                for symbol in config.symbols:
                    f = funding.get(symbol) or {}
                    if f.get("sha256"):
                        man["symbols"][symbol]["funding"] = {
                            "path": f.get("path"),
                            "sha256": f.get("sha256"),
                            "source": "OKX public funding-rate-history",
                            "actual_realized_rates": True,
                            "validation": {
                                "status": "PASS",
                                "rows": f.get("rows"),
                            },
                        }
                    rel = f"data/event_trend_v1/{Path(man['symbols'][symbol]['path']).name}"
                    man["symbols"][symbol]["path"] = rel
                man["requested_end"] = end
                manifest_path.write_text(json.dumps(man, indent=2), encoding="utf-8")
                candle_manifest = man
            except Exception as exc:
                errors.append(f"manifest_funding:{exc}")

    registry_result = None
    if seed_registry:
        registry_result = seed_paper_registry(registry_path, force=force_registry)

    status = "ok" if not errors else "partial"
    if candle_manifest is None and not skip_download:
        status = "fail"

    return {
        "sleeve": "ten_u_local_experiment",
        "formal_status": status,
        "strategy_id": STRATEGY_ID,
        "config_fingerprint": PersistentEventTrendConfig().fingerprint(),
        "data_dir": str(data_dir),
        "window": {"start": global_start, "end": end},
        "candle_manifest_status": (candle_manifest or {}).get("coverage_status"),
        "funding": {
            k: {kk: vv for kk, vv in v.items() if kk != "error"}
            if isinstance(v, dict)
            else v
            for k, v in funding.items()
        },
        "registry": registry_result,
        "errors": errors,
    }


def _bootstrap_majors(
    *,
    data_dir: Path,
    registry_path: Path,
    skip_download: bool,
    seed_registry: bool,
    force_registry: bool,
    history_days: int,
) -> dict[str, Any]:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    data = ensure_majors_15m_data(
        data_dir, skip_download=skip_download, days=history_days
    )
    registry_result = None
    if seed_registry:
        registry_result = seed_majors_registry(registry_path, force=force_registry)
    status = data.get("formal_status") or "ok"
    if registry_result is None and seed_registry:
        status = "fail"
    return {
        "sleeve": "majors_production_bound",
        "formal_status": status,
        "strategy_id": MAJORS_STRATEGY_ID,
        "config_fingerprint": MajorsSleeveConfig().fingerprint(),
        "data_dir": str(data_dir),
        "data": data,
        "registry": registry_result,
        "errors": list(data.get("errors") or []),
    }


def run_bootstrap(
    *,
    data_dir: Path | None = None,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    start_overrides: dict[str, str] | None = None,
    skip_download: bool = False,
    seed_registry: bool = True,
    force_registry: bool = False,
    mode: BootstrapMode = "majors",
    majors_data_dir: Path | None = None,
    ten_u_data_dir: Path | None = None,
    history_days: int = 120,
    write_handoff: bool = True,
) -> dict[str, Any]:
    """Cold-start server checkout. Default mode=majors (BTC/ETH production-bound)."""
    if mode not in {"majors", "ten_u", "both"}:
        raise ValueError(f"unsupported bootstrap mode: {mode}")

    # Backward compat: legacy callers pass data_dir as ten_u event_trend path
    majors_dir = majors_data_dir or Path("data")
    ten_u_dir = ten_u_data_dir or data_dir or Path("data/event_trend_v1")

    Path("reports/prod").mkdir(parents=True, exist_ok=True)
    sleeves: dict[str, Any] = {}
    errors: list[str] = []

    if mode in {"majors", "both"}:
        sleeves["majors"] = _bootstrap_majors(
            data_dir=majors_dir,
            registry_path=registry_path,
            skip_download=skip_download,
            seed_registry=seed_registry,
            force_registry=force_registry,
            history_days=history_days,
        )
        errors.extend(sleeves["majors"].get("errors") or [])

    if mode in {"ten_u", "both"}:
        sleeves["ten_u"] = _bootstrap_ten_u(
            data_dir=ten_u_dir,
            registry_path=registry_path,
            start_overrides=start_overrides,
            skip_download=skip_download,
            seed_registry=seed_registry,
            force_registry=force_registry,
        )
        errors.extend(sleeves["ten_u"].get("errors") or [])

    statuses = [s.get("formal_status") for s in sleeves.values()]
    if statuses and all(s == "ok" for s in statuses):
        formal = "ok"
    elif any(s == "ok" for s in statuses) or any(s == "partial" for s in statuses):
        formal = "partial"
    else:
        formal = "fail"

    handoff = None
    if write_handoff:
        handoff = write_server_handoff_contract(
            Path("reports/prod/server_handoff_contract.json")
        )

    next_commands = [
        "python -m prod.cli majors-hourly --commit-refresh",
        "python -m prod.cli ops-summary",
        "python -m prod.cli demo-checklist",
        "python -m prod.cli server-handoff",
    ]
    if mode in {"ten_u", "both"}:
        next_commands.append("python -m prod.cli run-ten-u  # legacy local_experiment only")

    return {
        "report_type": "server_bootstrap",
        "as_of": _utc_now(),
        "formal_status": formal,
        "mode": mode,
        "primary_sleeve": "majors_production_bound" if mode != "ten_u" else "ten_u_local_experiment",
        "sleeves": sleeves,
        "errors": errors,
        "places_exchange_orders": False,
        "live_allowed": False,
        "api_keys_written": False,
        "demo_live_execution_environment": "server_only",
        "handoff_contract_path": "reports/prod/server_handoff_contract.json"
        if handoff
        else None,
        "next_commands": next_commands,
        "notes": (
            "Bootstrap does not configure trading API keys. "
            "Server agent injects OKX_* only when enabling later demo/live."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap slim checkout on a server")
    parser.add_argument(
        "--mode",
        choices=["majors", "ten_u", "both"],
        default="majors",
        help="Default majors = BTC/ETH production-bound local paper",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Legacy ten_u data dir (default data/event_trend_v1 when mode includes ten_u)",
    )
    parser.add_argument("--majors-data", type=Path, default=Path("data"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--no-seed-registry", action="store_true")
    parser.add_argument("--force-registry", action="store_true")
    parser.add_argument("--history-days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("reports/prod/server_bootstrap.json"))
    args = parser.parse_args(argv)
    report = run_bootstrap(
        data_dir=args.data,
        majors_data_dir=args.majors_data,
        registry_path=args.registry,
        skip_download=args.skip_download,
        seed_registry=not args.no_seed_registry,
        force_registry=args.force_registry,
        mode=args.mode,
        history_days=args.history_days,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("formal_status") in {"ok", "partial"} else 1


if __name__ == "__main__":
    sys.exit(main())
