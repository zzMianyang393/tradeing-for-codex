"""OOS + multiwindow gates for batch-v7 interesting candidates."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_batch_majors_v7 import research_catalog_v7
from prod.research_sparse_oos import validate_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_v7_gates(
    data_dir: Path,
    *,
    names: list[str] | None = None,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
    batch_report_path: Path | None = None,
    formation_fracs: tuple[float, ...] = (0.50, 0.60, 0.70),
) -> dict[str, Any]:
    catalog = {c["name"]: c for c in research_catalog_v7()}
    if names:
        selected = names
    elif batch_report_path and batch_report_path.exists():
        batch = json.loads(batch_report_path.read_text(encoding="utf-8"))
        selected = list(batch.get("interesting") or [])
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
                    "decision": "reject",
                    "admit": False,
                    "blockers": ["unknown_name"],
                }
            )
            continue
        cfg = item["config"]
        tf = int(cfg.timeframe_minutes)
        embargo = max(1, 1440 // max(1, tf))
        sparse = (
            "dual_" in cfg.signal_family
            or "weekly" in cfg.signal_family
            or "outside" in cfg.signal_family
            or "failed" in cfg.signal_family
        )
        min_form = 8 if sparse else 12
        min_oos = 5 if sparse else 8

        windows = []
        for frac in formation_fracs:
            v = validate_config(
                data_dir,
                cfg,
                name=f"{name}@form{frac:.2f}",
                start_equity=start_equity,
                formation_frac=frac,
                embargo_bars=embargo,
                min_form_trades=min_form,
                min_oos_trades=min_oos,
            )
            windows.append(
                {
                    "formation_frac": frac,
                    "decision": v["decision"],
                    "blockers": v["blockers"],
                    "gates": v["gates"],
                    "full_sample": v["full_sample"],
                    "formation": v["formation"],
                    "oos": v["oos"],
                }
            )

        full = windows[0]["full_sample"]
        oos_n = sum(1 for w in windows if w["gates"]["oos_pass"])
        form_n = sum(1 for w in windows if w["gates"]["formation_pass"])
        full_ok = all(w["gates"]["full_pass"] for w in windows)
        trades = int(full.get("trades") or 0)
        ret = full.get("return_fraction")
        pf = full.get("profit_factor")

        # form_n >= 2: single formation pass is too weak (see h4 high-vol recent-only)
        admit = (
            full_ok
            and oos_n >= 2
            and form_n >= 2
            and trades >= 20
            and ret is not None
            and float(ret) >= 0.05
            and pf is not None
            and float(pf) >= 1.05
        )
        if admit:
            decision = "recommend_paper_prep_local_only"
        elif full_ok and oos_n >= 2 and trades >= 12:
            decision = "watchlist_fragile"
        elif full_ok and (ret is not None and float(ret) > 0):
            decision = "watchlist_weak"
        else:
            decision = "reject"

        results.append(
            {
                "name": name,
                "strategy_id": cfg.strategy_id,
                "signal_family": cfg.signal_family,
                "timeframe_minutes": tf,
                "config_fingerprint": cfg.fingerprint(),
                "windows": windows,
                "oos_pass_windows": oos_n,
                "formation_pass_windows": form_n,
                "window_count": len(windows),
                "full_ok": full_ok,
                "trades": trades,
                "full_return": ret,
                "full_pf": pf,
                "decision": decision,
                "admit": admit,
                "places_exchange_orders": False,
                "live_allowed": False,
            }
        )

    recommended = [r["name"] for r in results if r.get("admit")]
    return {
        "report_type": "research_v7_gates_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "selected_names": selected,
        "formation_fracs": list(formation_fracs),
        "recommended_paper_prep_local_only": recommended,
        "results": results,
        "places_exchange_orders": False,
        "live_allowed": False,
        "notes": [
            "Strict post-v5/v6 integrity bar: multiwindow OOS majority, "
            "formation>=1, trades>=20, full ret>=5%, PF>=1.05.",
            "Does not place orders or enable demo/live.",
        ],
    }


def write_v7_gates_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
