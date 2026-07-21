"""OOS validation for batch-v6 interesting / borderline candidates."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_batch_majors_v6 import research_catalog_v6
from prod.research_sparse_oos import validate_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_v6_interesting_oos(
    data_dir: Path,
    *,
    names: list[str] | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
    batch_report_path: Path | None = None,
) -> dict[str, Any]:
    """Validate named catalog items; default = interesting from batch report if present."""
    catalog = {c["name"]: c for c in research_catalog_v6()}
    selected: list[str]
    if names:
        selected = names
    elif batch_report_path and batch_report_path.exists():
        batch = json.loads(batch_report_path.read_text(encoding="utf-8"))
        selected = list(batch.get("interesting") or [])
        # also include weak watchlist for completeness
        for n in batch.get("watchlist_weak") or []:
            if n not in selected:
                selected.append(n)
    else:
        selected = list(catalog.keys())

    results: list[dict[str, Any]] = []
    for name in selected:
        item = catalog.get(name)
        if item is None:
            results.append(
                {
                    "name": name,
                    "decision": "reject_for_paper_prep",
                    "blockers": ["unknown_name"],
                    "places_exchange_orders": False,
                    "live_allowed": False,
                }
            )
            continue
        cfg = item["config"]
        tf = int(cfg.timeframe_minutes)
        # embargo ~1 day
        embargo = max(1, 1440 // max(1, tf))
        # sparse duals / weekly: looser trade floors
        sparse = "dual_" in cfg.signal_family or "weekly" in cfg.signal_family
        min_form = 8 if sparse else 12
        min_oos = 5 if sparse else 8
        v = validate_config(
            data_dir,
            cfg,
            name=name,
            start_equity=start_equity,
            formation_frac=0.60,
            embargo_bars=embargo,
            min_form_trades=min_form,
            min_oos_trades=min_oos,
        )
        results.append(v)

    recommended = [r["name"] for r in results if r.get("paper_prep_recommended")]
    return {
        "report_type": "research_v6_oos_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "selected_names": selected,
        "recommended_paper_prep_local_only": recommended,
        "results": results,
        "places_exchange_orders": False,
        "live_allowed": False,
        "notes": [
            "OOS of batch-v6 candidates. Local paper only if recommended.",
            "Does not admit demo/live.",
        ],
    }


def write_v6_oos_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
