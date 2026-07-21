"""Frozen, outcome-free contract for 90-day prospective factor evaluation."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any


EVALUATION_SPEC_VERSION = "v1.0.0"
OBSERVATION_HORIZON_DAYS = 90
ENTRY_DELAY_HOURS = 4
ROUND_TRIP_FRICTION_PCT = 0.16

# A burst of same-day triggers is not independent factor evidence.
MIN_MATURED_OBSERVATIONS = 10
MIN_DISTINCT_SIGNAL_DAYS = 5
MIN_CALENDAR_MONTHS = 2
MIN_DISTINCT_SYMBOLS = 3

# Stronger thresholds are required before a human may even consider paper eligibility.
MIN_PROSPECTIVE_CALENDAR_DAYS_FOR_PAPER_REVIEW = 365
MIN_MATURED_OBSERVATIONS_FOR_PAPER_REVIEW = 30
MIN_CALENDAR_MONTHS_FOR_PAPER_REVIEW = 4


def utc_day(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def utc_month(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m")


def evidence_readiness(observations: list[dict[str, Any]], as_of_ts: int) -> dict[str, Any]:
    """Assess only whether mature observations are diverse enough for sealed evaluation."""
    mature = [item for item in observations if int(item["maturity_ts"]) <= as_of_ts]
    days = Counter(utc_day(int(item["signal_ts"])) for item in mature)
    months = {utc_month(int(item["signal_ts"])) for item in mature}
    symbols = {str(item["symbol"]) for item in mature}
    return {
        "spec_version": EVALUATION_SPEC_VERSION,
        "matured_observation_count": len(mature),
        "distinct_signal_day_count": len(days),
        "calendar_month_count": len(months),
        "distinct_symbol_count": len(symbols),
        "minimum_evidence_ready": (
            len(mature) >= MIN_MATURED_OBSERVATIONS
            and len(days) >= MIN_DISTINCT_SIGNAL_DAYS
            and len(months) >= MIN_CALENDAR_MONTHS
            and len(symbols) >= MIN_DISTINCT_SYMBOLS
        ),
        "paper_review_ready": False,
        "observation_only": True,
    }
