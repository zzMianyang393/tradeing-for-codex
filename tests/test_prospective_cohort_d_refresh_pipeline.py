from pathlib import Path
from unittest.mock import patch

from prospective_cohort_d_cross_sectional_weakness import ACTIVATION_TS
from prospective_cohort_d_refresh_pipeline import build_registry, empty_checkpoint, maturity, run_pipeline, transactional_publish, validate_append_only


def signal(ts=ACTIVATION_TS):
    return {"cohort_id": "prospective_cohort_d_2026-07-16", "hypothesis_id": "weekly_cross_sectional_weakness_short_exploration_v1", "rule_version": "frozen_2026-07-16", "signal_ts": ts, "signal_timestamp_utc": "2026-07-20 00:00:00", "symbol": "BTC-USDT-SWAP", "direction": "short", "regime": "weekly_cross_sectional_rank", "trigger_metrics": {}, "observation_only": True}


def ledger(rows, cutoff="2026-07-20 00:00:00"):
    return {"cohort_id": signal()["cohort_id"], "hypothesis_id": signal()["hypothesis_id"], "common_data_cutoff": cutoff, "coverage_status": "active", "signals": rows, "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def test_append_only_rejects_backfill_and_mutation():
    first = build_registry(ledger([signal()])); checkpoint = {**empty_checkpoint(), "identities": {first["observations"][0]["observation_id"]: first["observations"][0]}, "current_count": 1, "max_signal_ts": ACTIVATION_TS}
    assert validate_append_only(empty_checkpoint(), build_registry(ledger([signal(ACTIVATION_TS - 1)])))["valid"] is False
    assert validate_append_only(checkpoint, build_registry(ledger([])))["valid"] is False
    assert validate_append_only(checkpoint, build_registry(ledger([{**signal(), "direction": "long"}])))["valid"] is False


def test_maturity_never_contains_outcomes():
    report = maturity(build_registry(ledger([signal()])))
    assert report["n_awaiting"] == 1 and report["outcomes_evaluated"] is False and report["observation_only"] is True


def test_pipeline_with_same_data_is_dry_run_no_changes(tmp_path):
    with patch("prospective_cohort_d_refresh_pipeline.build", return_value=ledger([])):
        result = run_pipeline(Path("data"), commit=False, reports_dir=tmp_path)
    assert result["refresh_decision"] == "no_changes" and result["published"] is False


def test_transaction_rolls_back_new_files(tmp_path):
    staging, formal = tmp_path / "staging", tmp_path / "formal"; staging.mkdir(); formal.mkdir()
    source = staging / "ledger.json"; source.write_text('{"v": 2}', encoding="utf-8")
    result = transactional_publish([(source, formal / "ledger.json")], {"v": 2}, formal / "checkpoint.json", fail_at=1)
    assert result["success"] is False and result["rollback_attempted"] is True
    assert not (formal / "ledger.json").exists() and not (formal / "checkpoint.json").exists()
