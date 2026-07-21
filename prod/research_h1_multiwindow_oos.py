"""Multi-window formation/OOS for admitted + dual 1h majors research sleeves.

Closes the dual watchlist decision with more than one split. Does not admit
trading. Uses native 1h BTC/ETH only.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.majors_contract import h1_md_mom_short_config, resolve_sleeve_config
from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_sparse_oos import validate_config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dual_config():
    return resolve_sleeve_config("prod_majors_h1_dual_md_mom_short_v1")


def candidate_specs() -> list[dict[str, Any]]:
    dual = _dual_config()
    assert dual is not None
    return [
        {
            "name": "h1_md_mom_short",
            "role": "admitted_primary",
            "config": h1_md_mom_short_config(),
            "min_form_trades": 15,
            "min_oos_trades": 10,
        },
        {
            "name": "h1_dual_md_mom_short",
            "role": "watchlist",
            "config": dual,
            "min_form_trades": 8,
            "min_oos_trades": 5,
        },
    ]


def run_h1_multiwindow_oos(
    data_dir: Path,
    *,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
    formation_fracs: tuple[float, ...] = (0.50, 0.60, 0.70),
    embargo_bars: int = 24,
) -> dict[str, Any]:
    """Run formation/OOS at multiple formation fractions (embargo ~1d on 1h)."""
    results: list[dict[str, Any]] = []
    for spec in candidate_specs():
        windows: list[dict[str, Any]] = []
        for frac in formation_fracs:
            v = validate_config(
                data_dir,
                spec["config"],
                name=f"{spec['name']}@form{frac:.2f}",
                start_equity=start_equity,
                formation_frac=frac,
                embargo_bars=embargo_bars,
                min_form_trades=int(spec["min_form_trades"]),
                min_oos_trades=int(spec["min_oos_trades"]),
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
                    "split": v["split"],
                    "paper_prep_recommended": v["paper_prep_recommended"],
                }
            )
        oos_pass_n = sum(1 for w in windows if w["gates"]["oos_pass"])
        form_pass_n = sum(1 for w in windows if w["gates"]["formation_pass"])
        full_pass = all(w["gates"]["full_pass"] for w in windows)
        majority = oos_pass_n >= (len(windows) + 1) // 2
        all_oos = oos_pass_n == len(windows)
        if full_pass and all_oos and form_pass_n == len(windows):
            aggregate = "robust_pass"
        elif full_pass and majority and form_pass_n >= 1:
            aggregate = "fragile_pass_majority_oos"
        elif full_pass and oos_pass_n == 0:
            aggregate = "reject_oos_fails_all_windows"
        else:
            aggregate = "reject_or_thin"

        # Dual-specific recommendation
        if spec["name"] == "h1_dual_md_mom_short":
            if aggregate == "robust_pass":
                dual_action = "eligible_for_secondary_paper_prep"
            elif aggregate == "fragile_pass_majority_oos":
                dual_action = "keep_watchlist_do_not_admit"
            else:
                dual_action = "drop_from_primary_path"
        else:
            if aggregate in {"robust_pass", "fragile_pass_majority_oos"}:
                dual_action = "keep_admitted_local_paper"
            else:
                dual_action = "revisit_admission"

        results.append(
            {
                "name": spec["name"],
                "role": spec["role"],
                "strategy_id": spec["config"].strategy_id,
                "config_fingerprint": spec["config"].fingerprint(),
                "windows": windows,
                "oos_pass_windows": oos_pass_n,
                "formation_pass_windows": form_pass_n,
                "window_count": len(windows),
                "aggregate_decision": aggregate,
                "action": dual_action,
                "places_exchange_orders": False,
                "live_allowed": False,
            }
        )

    return {
        "report_type": "h1_multiwindow_oos_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "timeframe_minutes": 60,
        "formation_fracs": list(formation_fracs),
        "embargo_bars": embargo_bars,
        "start_equity": start_equity,
        "results": results,
        "places_exchange_orders": False,
        "live_allowed": False,
        "notes": [
            "Multi-window OOS for admitted h1_md_mom_short and dual watchlist.",
            "Does not place orders or admit demo/live.",
            "Dual remains non-primary unless aggregate_decision=robust_pass.",
        ],
    }


def write_multiwindow_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
