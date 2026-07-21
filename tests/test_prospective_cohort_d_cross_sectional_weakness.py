from datetime import datetime, timezone

from market import Bar
from prospective_cohort_d_cross_sectional_weakness import (
    ACTIVATION_TS, ALLOWED_FIELDS, HYPOTHESIS_ID, signals_from_daily, validate,
)


def daily(ts: int, close: float) -> Bar:
    return Bar(ts, "", close, close, close, close, 0.0)


def test_future_monday_selects_exactly_three_weakest_symbols():
    monday = ACTIVATION_TS
    assert datetime.fromtimestamp(monday / 1000, tz=timezone.utc).weekday() == 0
    sunday, prior = monday - 86_400_000, monday - 29 * 86_400_000
    inputs = {
        f"S{i}-USDT-SWAP": [daily(prior, 100.0), daily(sunday, 100.0 + i)]
        for i in range(4)
    }
    rows = signals_from_daily(inputs, monday)
    assert [row["symbol"] for row in rows] == ["S0-USDT-SWAP", "S1-USDT-SWAP", "S2-USDT-SWAP"]
    assert all(row["direction"] == "short" and set(row) == ALLOWED_FIELDS for row in rows)


def test_pre_activation_rows_are_never_emitted():
    monday = ACTIVATION_TS - 7 * 86_400_000
    sunday, prior = monday - 86_400_000, monday - 29 * 86_400_000
    inputs = {f"S{i}-USDT-SWAP": [daily(prior, 100.0), daily(sunday, 101.0)] for i in range(3)}
    assert signals_from_daily(inputs, ACTIVATION_TS) == []


def test_validate_rejects_outcome_and_wrong_direction_fields():
    signal = {key: None for key in ALLOWED_FIELDS}
    signal.update({"cohort_id": "prospective_cohort_d_2026-07-16", "hypothesis_id": HYPOTHESIS_ID,
                   "rule_version": "frozen_2026-07-16", "signal_ts": ACTIVATION_TS,
                   "direction": "long", "trigger_metrics": {}, "observation_only": True})
    try:
        validate([signal])
    except ValueError:
        pass
    else:
        raise AssertionError("wrong direction must be rejected")
