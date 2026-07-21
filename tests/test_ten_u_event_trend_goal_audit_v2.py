import json
from pathlib import Path

from ten_u_event_trend_goal_audit_v2 import build_goal_audit


ROOT = Path(__file__).resolve().parents[1]


def test_goal_audit_does_not_claim_validation_or_live_readiness():
    report = build_goal_audit(ROOT)
    assert report["formal_status"] == "active_research_not_validated"
    assert report["requirements"]["high_return_10u_accumulation"]["status"] == "not_proven"
    assert report["requirements"]["avoid_stop_sweeps"]["status"] == "not_proven"
    assert report["requirements"]["paper_or_live_readiness"]["status"] == "not_authorized"


def test_goal_audit_proves_only_narrow_behavioral_invariant_complete():
    report = build_goal_audit(ROOT)
    assert report["proven_complete_requirements"] == ["single_coin_max_three_universe"]
    evidence = report["requirements"]["single_coin_max_three_universe"]["evidence"]
    assert len(evidence["symbols"]) == 3
    assert evidence["maximum_concurrent_positions"] == 1


def test_goal_audit_keeps_prospective_outcomes_sealed():
    report = build_goal_audit(ROOT)
    assert report["outcome_metrics_computed_from_prospective_data"] is False
    anti_overfit = report["requirements"]["avoid_overfitting"]["evidence"]
    assert anti_overfit["prospective_outcomes_accessed"] is False
    assert anti_overfit["stage_one_records_reusable_in_stage_two"] is False


def test_historical_windfall_is_explicitly_small_sample_not_proof():
    evidence = build_goal_audit(ROOT)["requirements"]["high_return_10u_accumulation"]["evidence"]
    assert evidence["historical_ending_equity"] > evidence["historical_starting_equity"]
    assert evidence["historical_trades"] == 3
    assert evidence["historical_formal_status"] == "sealed_screen_insufficient_evidence"


def test_stored_goal_audit_is_an_honest_immutable_snapshot():
    stored = json.loads(
        (ROOT / "reports/ten_u_event_trend_goal_audit_v2.json").read_text(encoding="utf-8")
    )
    current = build_goal_audit(ROOT)
    assert stored["report_type"] == current["report_type"]
    assert stored["config_fingerprint"] == current["config_fingerprint"]
    assert stored["formal_status"] == "active_research_not_validated"
    assert stored["outcome_metrics_computed_from_prospective_data"] is False
    assert stored["requirements"]["paper_or_live_readiness"]["status"] == "not_authorized"
