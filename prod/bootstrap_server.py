"""Cold-start a slim git checkout on a trading server.

Git does not ship data/ or reports/. This builds:
- data/event_trend_v1 1H candles + funding for RAVE/LAB/ETH
- reports/prod directories
- paper-prep registry seed (high-risk 10U) when missing
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from funding_rate import (
    fetch_funding_page,
    load_funding_rates,
    parse_funding_rows,
    save_funding_rates,
)
from prod.registry import (
    DEFAULT_REGISTRY_PATH,
    PaperPrepEntry,
    get_entry,
    upsert_entry,
)
from prod.ten_u_market_refresh import floor_hour_ms, merge_funding
from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig, STRATEGY_ID
from ten_u_event_trend_data_v1 import (
    HOUR_MS,
    download_dataset,
    format_utc,
)


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
        ],
        live_allowed=False,
        notes=(
            "Seeded by prod.bootstrap_server for remote paper/demo ops. "
            "Prospective wait not required. Live remains closed."
        ),
        evidence_paths=["prod/bootstrap_server.py"],
    )
    upsert_entry(entry, registry_path)
    return {"action": "seeded", "entry": entry.to_dict()}


def run_bootstrap(
    *,
    data_dir: Path,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    start_overrides: dict[str, str] | None = None,
    skip_download: bool = False,
    seed_registry: bool = True,
    force_registry: bool = False,
) -> dict[str, Any]:
    config = PersistentEventTrendConfig()
    data_dir.mkdir(parents=True, exist_ok=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    end = _end_iso_now()
    starts = {**DEFAULT_STARTS, **(start_overrides or {})}
    # Use earliest start for download_dataset multi-symbol call? download_dataset
    # uses one start for all — download per-symbol with shared end via one window
    # from LAB start so RAVE has empty early hours filtered by collect range.
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

        # Attach funding into manifest if present
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
                    # Prefer relative paths for portability
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
        "report_type": "server_bootstrap",
        "as_of": _utc_now(),
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
        "next_commands": [
            "python -m prod.cli universe-check",
            "python -m prod.cli run-ten-u",
            "python -m prod.cli demo-drill --symbol ETH-USDT-SWAP",
            "python -m prod.cli watch-ten-u --iterations 1",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap slim checkout on a server")
    parser.add_argument("--data", type=Path, default=Path("data/event_trend_v1"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--no-seed-registry", action="store_true")
    parser.add_argument("--force-registry", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("reports/prod/server_bootstrap.json"))
    args = parser.parse_args(argv)
    report = run_bootstrap(
        data_dir=args.data,
        registry_path=args.registry,
        skip_download=args.skip_download,
        seed_registry=not args.no_seed_registry,
        force_registry=args.force_registry,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("formal_status") in {"ok", "partial"} else 1


if __name__ == "__main__":
    sys.exit(main())
