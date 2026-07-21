from __future__ import annotations

from prospective_sealed_evaluation_spec import (
    ENTRY_DELAY_HOURS,
    EVALUATION_SPEC_VERSION,
    MIN_CALENDAR_MONTHS,
    MIN_DISTINCT_SIGNAL_DAYS,
    MIN_DISTINCT_SYMBOLS,
    MIN_MATURED_OBSERVATIONS,
    OBSERVATION_HORIZON_DAYS,
    ROUND_TRIP_FRICTION_PCT,
    evidence_readiness,
)


DAY_MS = 24 * 60 * 60 * 1000


def _observation(day: int, symbol: str) -> dict:
    signal_ts = day * DAY_MS
    return {"signal_ts": signal_ts, "maturity_ts": signal_ts + OBSERVATION_HORIZON_DAYS * DAY_MS, "symbol": symbol}


def test_frozen_evaluation_contract_constants() -> None:
    assert EVALUATION_SPEC_VERSION == "v1.0.0"
    assert OBSERVATION_HORIZON_DAYS == 90
    assert ENTRY_DELAY_HOURS == 4
    assert ROUND_TRIP_FRICTION_PCT == 0.16


def test_same_day_burst_is_not_minimum_evidence() -> None:
    observations = [_observation(0, f"S{i}") for i in range(MIN_MATURED_OBSERVATIONS)]
    readiness = evidence_readiness(observations, 90 * DAY_MS)
    assert readiness["matured_observation_count"] == MIN_MATURED_OBSERVATIONS
    assert readiness["distinct_signal_day_count"] == 1
    assert readiness["minimum_evidence_ready"] is False
    assert readiness["paper_review_ready"] is False


def test_diverse_mature_observations_can_reach_minimum_evidence_only() -> None:
    observations = [_observation(day * 10, f"S{day % MIN_DISTINCT_SYMBOLS}") for day in range(MIN_MATURED_OBSERVATIONS)]
    readiness = evidence_readiness(observations, (90 + 100) * DAY_MS)
    assert readiness["distinct_signal_day_count"] >= MIN_DISTINCT_SIGNAL_DAYS
    assert readiness["calendar_month_count"] >= MIN_CALENDAR_MONTHS
    assert readiness["distinct_symbol_count"] == MIN_DISTINCT_SYMBOLS
    assert readiness["minimum_evidence_ready"] is True
    assert readiness["paper_review_ready"] is False
