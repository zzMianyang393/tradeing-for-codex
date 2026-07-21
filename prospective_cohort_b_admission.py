"""Frozen admission manifest for the second prospective signal cohort.

This module deliberately does not generate signals or evaluate outcomes.  It
records the boundary between the original 28-observation cohort and rules that
were admitted later, so a new rule can never be silently backfilled into the
first cohort.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


COHORT_ID = "prospective_cohort_b_2026-07-14"
COHORT_START_UTC = "2026-07-14 00:00:00"
COHORT_A_CUTOFF_UTC = "2026-07-13 08:15:00"
OBSERVATION_HORIZON_DAYS = 90

# These are pre-registered research candidates, not strategies or paper-trade
# candidates.  Signal generation is intentionally a later, separately tested
# step after data coverage reaches the cohort start.
COHORT_B_CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "daily_rsi_downtrend_rebound_v1",
        "source_research_id": "daily_rsi_mean_revert",
        "role": "directional_weak_signal",
        "direction": "long",
        "declared_regimes": ["趋势下行"],
        "rule": "Daily RSI(14) < 35; observe a long trigger at the next completed daily open; max horizon 10 days.",
        "data_requirements": ["OKX 15m OHLCV resampled to daily", "completed 4h regime label"],
        "historical_status": "posthoc_regime_repair_requires_future_window",
        "reason_for_admission": "The repaired downtrend-only audit has adequate historical event coverage, but it remains unapproved until this new prospective cohort matures.",
        "known_overlap": ["ema_continuation_short_downtrend_v1"],
        "overlap_type": "opposite_direction",
    },
    {
        "candidate_id": "daily_volatility_expansion_continuation_v1",
        "source_research_id": "VS_05",
        "role": "directional_weak_signal",
        "direction": "rule_determined",
        "declared_regimes": ["高波动转换"],
        "rule": "Frozen research card required before generation: daily true range expansion relative to prior ATR, with direction determined only by the completed daily close location.",
        "data_requirements": ["OKX 15m OHLCV resampled to daily", "completed 4h regime label"],
        "historical_status": "not_yet_audited",
        "reason_for_admission": "A low-turnover volatility-expansion mechanism can fill the high-volatility sleeve without reusing a time-of-day breakout.",
        "known_overlap": ["daily_volume_shock_reversal_v1_short"],
        "overlap_type": "semantic_only",
    },
    {
        "candidate_id": "daily_failed_breakout_reversal_v1",
        "source_research_id": "BO_10",
        "role": "directional_weak_signal",
        "direction": "short",
        "declared_regimes": ["高波动转换"],
        "rule": "Frozen research card required before generation: a completed daily upside breakout that closes back inside its prior channel emits a next-day short observation.",
        "data_requirements": ["OKX 15m OHLCV resampled to daily", "completed 4h regime label"],
        "historical_status": "not_yet_audited",
        "reason_for_admission": "Failure-reversal is structurally distinct from trend continuation and supplies a counter-trend hypothesis for transition markets.",
        "known_overlap": ["daily_volume_shock_reversal_v1_short"],
        "overlap_type": "semantic_only",
    },
)


def build_manifest() -> dict[str, Any]:
    """Return the immutable, signal-free admission record for Cohort B."""
    return {
        "report_type": "prospective_cohort_admission_manifest",
        "cohort_id": COHORT_ID,
        "cohort_start_utc": COHORT_START_UTC,
        "prior_cohort_cutoff_utc": COHORT_A_CUTOFF_UTC,
        "observation_horizon_days": OBSERVATION_HORIZON_DAYS,
        "candidate_count": len(COHORT_B_CANDIDATES),
        "candidates": list(COHORT_B_CANDIDATES),
        "admission_conditions": [
            "No signal with signal_ts before cohort_start_utc may be written into this cohort.",
            "No candidate may generate a signal before its frozen research card and signal-only generator tests exist.",
            "The first cohort and its 28 observations remain immutable and are never reclassified.",
            "All records remain observation-only; no position, entry price, exit, return, PnL, or paper eligibility may be stored.",
            "A candidate remains excluded if its frozen rule requires blocked data, grid/martingale logic, or a multi-leg cost-sensitive trade.",
        ],
        "outcomes_evaluated": False,
        "positions_opened": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def write_manifest(path: Path) -> dict[str, Any]:
    manifest = build_manifest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    output = Path("reports/prospective_cohort_b_admission_manifest.json")
    manifest = write_manifest(output)
    print(f"Manifest written to {output}; candidates={manifest['candidate_count']}; outcomes_evaluated=false")
