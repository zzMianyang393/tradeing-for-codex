from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from prospective_cohort_c_refresh_pipeline import (
    ACTIVATION_TS,
    build_registry,
    empty_checkpoint,
    identity,
    maturity,
    run_pipeline,
    transactional_publish,
    validate_append_only,
)


def signal(ts: int = ACTIVATION_TS) -> dict:
    return {
        "cohort_id": "prospective_cohort_c_2026-07-15",
        "hypothesis_id": "daily_volatility_expansion_short_exploration_v1",
        "rule_version": "frozen_2026-07-15",
        "signal_ts": ts,
        "signal_timestamp_utc": "2026-07-16 00:00:00",
        "symbol": "BTC-USDT-SWAP",
        "direction": "short",
        "regime": "高波动转换",
        "trigger_metrics": {},
        "observation_only": True,
    }


def ledger(signals: list[dict], cutoff: str = "2026-07-16 00:00:00") -> dict:
    return {"cohort_id": "prospective_cohort_c_2026-07-15", "hypothesis_id": signal()["hypothesis_id"], "common_data_cutoff": cutoff, "coverage_status": "awaiting_data_coverage", "signals": signals, "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def test_empty_pre_activation_pipeline_is_dry_run_only(tmp_path):
    pre_activation_ledger = ledger([], cutoff="2026-07-15 07:15:00")
    with patch("prospective_cohort_c_refresh_pipeline.build", return_value=pre_activation_ledger):
        result = run_pipeline(Path("data"), commit=False, reports_dir=tmp_path)
    assert result["coverage_status"] == "awaiting_data_coverage"
    cutoff_ts = int(
        datetime.strptime(result["common_data_cutoff"], "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc).timestamp() * 1000
    )
    assert cutoff_ts < ACTIVATION_TS
    assert result["refresh_decision"] == "no_changes"
    assert result["new_observations"] == 0
    assert result["published"] is False


def test_new_post_activation_observation_is_appendable():
    registry = build_registry(ledger([signal()]))
    check = validate_append_only(empty_checkpoint(), registry)
    assert check["valid"] is True
    assert check["new_count"] == 1


def test_pre_activation_observation_is_rejected():
    bad = signal(ACTIVATION_TS - 1)
    registry = build_registry(ledger([bad]))
    check = validate_append_only(empty_checkpoint(), registry)
    assert check["valid"] is False
    assert any("predates activation" in issue for issue in check["issues"])


def test_existing_observation_cannot_change_or_disappear():
    first = build_registry(ledger([signal()]))
    checkpoint = {**empty_checkpoint(), "identities": {first["observations"][0]["observation_id"]: first["observations"][0]}, "current_count": 1, "max_signal_ts": ACTIVATION_TS}
    changed = build_registry(ledger([{**signal(), "direction": "long"}]))
    assert validate_append_only(checkpoint, changed)["valid"] is False
    assert validate_append_only(checkpoint, build_registry(ledger([])))["valid"] is False


def test_maturity_has_no_outcomes_or_positions():
    report = maturity(build_registry(ledger([signal()])))
    assert report["n_awaiting"] == 1
    assert report["outcomes_evaluated"] is False
    assert report["observation_only"] is True


def test_transaction_rolls_back_new_files_on_injected_failure(tmp_path):
    staging, formal = tmp_path / "staging", tmp_path / "formal"
    staging.mkdir(); formal.mkdir()
    source = staging / "ledger.json"; source.write_text('{"v": 2}', encoding="utf-8")
    destination, checkpoint = formal / "ledger.json", formal / "checkpoint.json"
    outcome = transactional_publish([(source, destination)], {"v": 2}, checkpoint, fail_at=1)
    assert outcome["success"] is False
    assert outcome["rollback_attempted"] is True
    assert not destination.exists()
    assert not checkpoint.exists()


def test_no_runner_import_and_identity_is_stable():
    content = Path("prospective_cohort_c_refresh_pipeline.py").read_text(encoding="utf-8")
    assert "from runner import" not in content
    assert "import runner" not in content
    assert identity(signal()) == identity(signal())
