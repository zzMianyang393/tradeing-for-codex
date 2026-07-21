from __future__ import annotations

from prospective_cohort_b_admission import (
    COHORT_A_CUTOFF_UTC,
    COHORT_B_CANDIDATES,
    COHORT_ID,
    COHORT_START_UTC,
    build_manifest,
)


def test_cohort_b_starts_after_the_original_cohort_cutoff() -> None:
    assert COHORT_START_UTC > COHORT_A_CUTOFF_UTC


def test_cohort_b_is_a_small_mechanism_distinct_research_batch() -> None:
    assert [item["candidate_id"] for item in COHORT_B_CANDIDATES] == [
        "daily_rsi_downtrend_rebound_v1",
        "daily_volatility_expansion_continuation_v1",
        "daily_failed_breakout_reversal_v1",
    ]
    assert {item["source_research_id"] for item in COHORT_B_CANDIDATES} == {
        "daily_rsi_mean_revert",
        "VS_05",
        "BO_10",
    }


def test_manifest_remains_observation_only_and_not_paper_eligible() -> None:
    manifest = build_manifest()
    forbidden_fields = {"entry_price", "exit_price", "pnl", "return", "position", "order"}
    assert manifest["cohort_id"] == COHORT_ID
    assert manifest["outcomes_evaluated"] is False
    assert manifest["positions_opened"] is False
    assert manifest["safety_gates"]["approved_for_paper"] == []
    assert manifest["safety_gates"]["safe_to_enable_trading"] is False
    assert not (forbidden_fields & set(manifest))
    for candidate in manifest["candidates"]:
        assert not (forbidden_fields & set(candidate))


def test_only_the_repaired_rsi_candidate_is_allowed_to_have_historical_audit() -> None:
    candidates = {item["candidate_id"]: item for item in COHORT_B_CANDIDATES}
    assert candidates["daily_rsi_downtrend_rebound_v1"]["historical_status"] == "posthoc_regime_repair_requires_future_window"
    assert candidates["daily_volatility_expansion_continuation_v1"]["historical_status"] == "not_yet_audited"
    assert candidates["daily_failed_breakout_reversal_v1"]["historical_status"] == "not_yet_audited"
