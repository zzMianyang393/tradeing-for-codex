"""Server agent handoff contract (machine-readable).

Research workstation does NOT configure trading API keys.
Demo/live run only on the server with agent-injected secrets.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from prod.majors_contract import (
    STRATEGY_ID as MAJORS_STRATEGY_ID,
    MajorsSleeveConfig,
    h1_high_vol_donchian_short_config,
    h1_md_mom_short_config,
)
from prod.policy import (
    DEFAULT_START_EQUITY_USDT,
    MAX_START_EQUITY_USDT,
    PRODUCTION_BOUND_SYMBOLS,
    operator_policy_snapshot,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_server_handoff_contract() -> dict[str, Any]:
    """Pure: commands, paths, env names for the server agent."""
    cfg = MajorsSleeveConfig()
    policy = operator_policy_snapshot()
    return {
        "report_type": "server_agent_handoff_contract",
        "as_of": _utc_now(),
        "version": "v1",
        "execution_split": {
            "research_workstation": [
                "strategy research and backtests",
                "local paper fingerprints and readiness packages",
                "git push of code only",
            ],
            "research_workstation_forbidden": [
                "OKX demo/live trading",
                "storing or configuring trading API keys",
            ],
            "server": [
                "git pull",
                "bootstrap data and paper registry",
                "scheduled majors local paper",
                "later demo/live with agent-injected keys",
            ],
            "server_only_secrets": [
                "OKX_API_KEY",
                "OKX_API_SECRET",
                "OKX_API_PASSPHRASE",
            ],
        },
        "operator_policy": policy,
        "production_bound": {
            "strategy_id": MAJORS_STRATEGY_ID,
            "symbols": sorted(PRODUCTION_BOUND_SYMBOLS),
            "start_equity_usdt_default": DEFAULT_START_EQUITY_USDT,
            "start_equity_usdt_max": MAX_START_EQUITY_USDT,
            "config_fingerprint": cfg.fingerprint(),
            "timeframe": "15m",
            "registry_status": "suspended",
            "notes": (
                "SUSPENDED 2026-07-17 after multiwindow health: full-sample ~-67% "
                "peak_drawdown_halt. Do not schedule majors-hourly paper for this id "
                "until re-admitted with a passing strategy."
            ),
            "evidence": "docs/research_majors_primary_health_2026-07-17.md",
        },
        "research_sleeves_local_paper": {
            "h1_high_vol_donchian_short": {
                "strategy_id": "prod_majors_h1_high_vol_donchian_short_v1",
                "timeframe": "1h",
                "okx_bar": "1H",
                "status": "paper_prep",
                "live_allowed": False,
                "config_fingerprint": h1_high_vol_donchian_short_config().fingerprint(),
                "state_path": "reports/prod/h1_high_vol_donchian_short_paper_state.json",
                "cycle_path": "reports/prod/h1_high_vol_donchian_short_paper_cycle.json",
                "lock_path": "reports/prod/h1_high_vol_donchian_short_runtime.lock",
                "hourly_job_report": "reports/prod/h1_high_vol_donchian_short_hourly_job.json",
                "notes": (
                    "Admitted 2026-07-17 after v7 multiwindow + year positives. "
                    "Local paper only. Do not retune. Not demo/live."
                ),
                "evidence": "docs/research_batch_majors_v7_result.md",
            },
            "h1_md_mom_short": {
                "strategy_id": "prod_majors_h1_md_mom_short_v1",
                "timeframe": "1h",
                "okx_bar": "1H",
                "status": "rejected",
                "live_allowed": False,
                "config_fingerprint": h1_md_mom_short_config().fingerprint(),
                "notes": (
                    "REVOKED 2026-07-17: corrupt ETH 1h timestamps false edge. "
                    "Do not schedule. Not demo/live."
                ),
                "evidence": "docs/research_h1_data_integrity_revoke_2026-07-17.md",
            },
        },
        "paths": {
            "majors_data_dir": "data",
            "majors_btc_15m": "data/BTC_15m.csv",
            "majors_eth_15m": "data/ETH_15m.csv",
            "majors_btc_1h": "data/BTC_1h.csv",
            "majors_eth_1h": "data/ETH_1h.csv",
            "registry": "reports/prod/paper_prep_registry.json",
            "majors_paper_state": "reports/prod/majors_paper_state.json",
            "majors_paper_cycle": "reports/prod/majors_paper_cycle.json",
            "majors_runtime_lock": "reports/prod/majors_runtime.lock",
            "ops_dashboard": "reports/prod/ops_dashboard.json",
            "readiness_package": "reports/prod/majors_local_readiness_package.json",
            "hourly_job_report": "reports/prod/majors_hourly_job.json",
            "handoff_contract": "reports/prod/server_handoff_contract.json",
            "legacy_ten_u_data": "data/event_trend_v1",
        },
        "commands": {
            "cold_start_majors": [
                "python -m prod.cli bootstrap-server --mode majors",
            ],
            "daily_or_hourly_paper": [
                "# primary sleeve SUSPENDED — refresh data only until new strategy admitted",
                "python -m prod.cli majors-refresh-15m --commit",
                "python -m prod.cli majors-refresh-1h --commit",
                "# python -m prod.cli majors-hourly --commit-refresh  # blocked: not in paper_prep",
            ],
            "h1_research_paper_hourly": [
                (
                    "python -m prod.cli majors-hourly "
                    "--strategy-id prod_majors_h1_high_vol_donchian_short_v1 "
                    "--state reports/prod/h1_high_vol_donchian_short_paper_state.json "
                    "--cycle-out reports/prod/h1_high_vol_donchian_short_paper_cycle.json "
                    "--lock reports/prod/h1_high_vol_donchian_short_runtime.lock "
                    "--out reports/prod/h1_high_vol_donchian_short_hourly_job.json "
                    "--commit-refresh"
                ),
                "python -m prod.cli majors-refresh-1h --commit",
            ],
            "ops_snapshot": [
                "python -m prod.cli ops-summary",
                "python -m prod.cli status",
            ],
            "engineering_gate_for_later_demo": [
                "python -m prod.cli demo-checklist",
            ],
            "legacy_ten_u_optional": [
                "python -m prod.cli bootstrap-server --mode ten_u",
                "python -m prod.cli run-ten-u",
            ],
            "demo_live_server_only_later": [
                "# agent injects OKX_* into the environment first",
                "python -m prod.cli demo-drill --symbol ETH-USDT-SWAP",
                "# strategy auto-loop remains separate promotion — not default",
            ],
        },
        "cron_example": {
            "schedule": "5 * * * *",
            "command": (
                "cd /path/to/tradering && "
                "/usr/bin/python3 -m prod.cli majors-hourly --commit-refresh "
                ">> /var/log/tradering-majors-hourly.log 2>&1"
            ),
        },
        "cron_example_h1_research": {
            "schedule": "8 * * * *",
            "command": (
                "cd /path/to/tradering && "
                "/usr/bin/python3 -m prod.cli majors-hourly "
                "--strategy-id prod_majors_h1_high_vol_donchian_short_v1 "
                "--state reports/prod/h1_high_vol_donchian_short_paper_state.json "
                "--cycle-out reports/prod/h1_high_vol_donchian_short_paper_cycle.json "
                "--lock reports/prod/h1_high_vol_donchian_short_runtime.lock "
                "--out reports/prod/h1_high_vol_donchian_short_hourly_job.json "
                "--commit-refresh "
                ">> /var/log/tradering-majors-h1-hv-hourly.log 2>&1"
            ),
        },
        "windows_task_example": {
            "script": "scripts/prod_majors_hourly.ps1",
            "note": "15m primary SUSPENDED — prefer h1 research script if paper_prep",
        },
        "windows_task_example_h1_research": {
            "script": "scripts/prod_majors_h1_high_vol_hourly.ps1",
            "note": "1h high_vol donchian short paper; no API keys",
        },
        "invariants": {
            "places_exchange_orders_default": False,
            "live_allowed_default": False,
            "demo_live_execution_environment": "server_only",
            "api_keys_on_research_workstation": False,
            "rave_lab_not_graduation_eligible": True,
        },
        "notes": [
            "15m donchian primary is SUSPENDED (health check failed). ops-summary default sleeve shows degraded/registry_blocked — expected.",
            "Active research paper_prep: prod_majors_h1_high_vol_donchian_short_v1 (local only; separate state/lock).",
            "Hourly: scripts/prod_majors_h1_high_vol_hourly.ps1 or majors-hourly --strategy-id prod_majors_h1_high_vol_donchian_short_v1 ...",
            "Capital ladder 10/100/500 scale-invariant; operate at 10U baseline.",
            "1h multi_day_momentum_short remains REJECTED (data integrity).",
            "Ten-u RAVE/LAB is legacy local_experiment only.",
            "Research status: docs/STRATEGY_RESEARCH_STATUS_2026-07-17.md",
            "Passing demo-checklist means code/universe readiness for server agent — not local trading.",
            "Never commit OKX_* secrets to git.",
        ],
    }


def write_server_handoff_contract(
    path: Path = Path("reports/prod/server_handoff_contract.json"),
) -> dict[str, Any]:
    report = build_server_handoff_contract()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
