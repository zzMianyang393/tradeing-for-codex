"""One safe entry point for the daily data and prospective-observation cycle.

Default mode never appends market data.  ``--commit-data`` is explicit and
only commits an already-validated contiguous OKX append plan.  Cohort B and C
remain dry-run by default.  Cohort C observation publication requires a
separate explicit flag and never enables paper or live trading.
"""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
from typing import Any, Callable

from cohort_b_signal_only_refresh import refresh as refresh_cohort_b
from data_quality_audit import build_report as build_quality_report
from prospective_cutoff_alignment_audit import build as build_cutoff_alignment, load_json as load_alignment_json
from okx_downloader import fetch_page
from okx_incremental_15m_refresh import build_plan, commit_plan
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from prospective_cohort_c_refresh_pipeline import run_pipeline as refresh_cohort_c
from research_state_dashboard import build_dashboard, generate_markdown


REPORTS = Path("reports")


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def quality_is_valid(report: dict[str, Any]) -> bool:
    summary = report.get("summary", {})
    return (
        report.get("n_audited") == report.get("n_eligible_symbols")
        and summary.get("total_gaps") == 0
        and summary.get("total_duplicates") == 0
    )


def compact_data_refresh(plan: dict[str, Any]) -> dict[str, Any]:
    """Keep the cycle report free of raw bars and market values."""
    items = plan.get("symbols", [])
    return {
        "symbol_count": plan.get("symbol_count", 0),
        "total_append_count": plan.get("total_append_count", 0),
        "all_contiguous": plan.get("all_contiguous", False),
        "committed": plan.get("committed", False),
        "append_count_distribution": sorted({item.get("append_count", 0) for item in items}),
        "local_last_utc": sorted({item.get("local_last_utc", "") for item in items}),
        "new_last_utc": sorted({item.get("new_last_utc", "") for item in items}),
    }


def write_dashboard(reports_dir: Path) -> None:
    dashboard = build_dashboard()
    save_json(reports_dir / "research_state_dashboard.json", dashboard)
    (reports_dir.parent / "docs" / f"research_state_dashboard_{dashboard['generation_date']}.md").write_text(
        generate_markdown(dashboard), encoding="utf-8"
    )


def run_cycle(
    data_dir: Path,
    commit_data: bool = False,
    fetch: Callable[..., list[list[str]]] = fetch_page,
    reports_dir: Path = REPORTS,
    fetch_workers: int = 4,
    commit_cohort_c_observations: bool = False,
) -> dict[str, Any]:
    """Run refresh -> quality gate -> B/C observation refresh -> dashboard in order."""
    if commit_cohort_c_observations and not commit_data:
        raise ValueError("Cohort C observation publication requires committed source data.")
    raw_plan = build_plan(data_dir, DEFAULT_SYMBOLS, fetch, workers=fetch_workers)
    if commit_data:
        raw_plan = commit_plan(raw_plan)
    data_refresh = compact_data_refresh(raw_plan)
    save_json(reports_dir / "okx_incremental_15m_refresh.json", raw_plan)

    quality = build_quality_report(data_dir)
    save_json(reports_dir / "data_quality_audit.json", quality)
    result: dict[str, Any] = {
        "cycle_type": "prospective_daily_observation_cycle",
        "observation_only": True,
        "data_mode": "commit" if commit_data else "dry_run",
        "data_refresh": data_refresh,
        "quality_gate": {
            "valid": quality_is_valid(quality),
            "common_data_cutoff": quality.get("common_cutoff_utc", ""),
            "total_gaps": quality.get("summary", {}).get("total_gaps", 0),
            "total_duplicates": quality.get("summary", {}).get("total_duplicates", 0),
        },
        "cohort_b": {"executed": False},
        "cohort_c": {"executed": False, "publication_requested": commit_cohort_c_observations},
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }
    # The refresh plan and full quality detail are already serialized; release them before
    # the independent Cohort readers load the same long-lived archives.
    del raw_plan
    del quality
    gc.collect()
    if not result["quality_gate"]["valid"]:
        result["cycle_decision"] = "quality_rejected_no_cohort_refresh"
        save_json(reports_dir / "prospective_daily_observation_cycle.json", result)
        return result

    cohort_b = refresh_cohort_b(data_dir, reports_dir, known_common_cutoff=result["quality_gate"]["common_data_cutoff"])
    cohort_c = refresh_cohort_c(data_dir, commit=commit_cohort_c_observations, reports_dir=reports_dir)
    result["cohort_b"] = {
        "executed": True,
        "decision": cohort_b.get("pipeline_decision"),
        "new_observations": cohort_b.get("new_observations"),
        "published": cohort_b.get("published"),
    }
    result["cohort_c"] = {
        "executed": True,
        "decision": cohort_c.get("refresh_decision"),
        "new_observations": cohort_c.get("new_observations"),
        "published": cohort_c.get("published"),
        "publication_requested": commit_cohort_c_observations,
    }
    cutoff_alignment = build_cutoff_alignment(
        {"common_cutoff_utc": result["quality_gate"]["common_data_cutoff"]},
        load_alignment_json(reports_dir / "cohort_b_signal_only_refresh.json"),
        cohort_c,
    )
    save_json(reports_dir / "prospective_cutoff_alignment_audit.json", cutoff_alignment)
    result["cutoff_alignment"] = {
        "status": cutoff_alignment["alignment_status"],
        "issues": cutoff_alignment["issues"],
    }
    result["cycle_decision"] = "completed_observation_dry_runs"
    save_json(reports_dir / "prospective_daily_observation_cycle.json", result)
    write_dashboard(reports_dir)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run safe daily prospective observation cycle.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--commit-data", action="store_true")
    parser.add_argument("--commit-cohort-c-observations", action="store_true")
    parser.add_argument("--fetch-workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.commit_cohort_c_observations and not args.commit_data:
        parser.error("--commit-cohort-c-observations requires --commit-data")
    result = run_cycle(
        args.data,
        commit_data=args.commit_data,
        fetch_workers=args.fetch_workers,
        commit_cohort_c_observations=args.commit_cohort_c_observations,
    )
    print(f"decision={result['cycle_decision']}; data_committed={result['data_refresh']['committed']}; b={result['cohort_b']['executed']}; c={result['cohort_c']['executed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
