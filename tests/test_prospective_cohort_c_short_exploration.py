from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from market import load_quantify_15m_csv
from prospective_cohort_c_short_exploration import ACTIVATION_TS, DEFAULT_STAGING_OUT, HYPOTHESIS_ID, common_cutoff, registry, signals_for_path, signals_for_symbol, validate


def signal(ts=ACTIVATION_TS):
    return {"cohort_id": "prospective_cohort_c_2026-07-15", "hypothesis_id": HYPOTHESIS_ID, "rule_version": "frozen_2026-07-15",
            "signal_ts": ts, "signal_timestamp_utc": "2026-07-16 00:00:00", "symbol": "BTC-USDT-SWAP", "direction": "short",
            "regime": "高波动转换", "trigger_metrics": {"true_range_to_prior_atr": 2.0, "close_location": 0.2}, "observation_only": True}


def test_registry_is_non_backfill_and_not_approved():
    report = registry()
    assert report["non_backfill"] is True
    assert report["safety_gates"]["approved_for_paper"] == []


def test_validate_rejects_pre_activation_or_wrong_direction():
    with pytest.raises(ValueError):
        validate([signal(ACTIVATION_TS - 1)])
    wrong = signal()
    wrong["direction"] = "long"
    with pytest.raises(ValueError):
        validate([wrong])


def test_validate_rejects_outcome_fields():
    row = signal()
    row["pnl"] = 1.0
    with pytest.raises(ValueError):
        validate([row])


def test_common_cutoff_reads_latest_csv_rows_without_loading_full_history(tmp_path):
    (tmp_path / "BTC_15m.csv").write_text("timestamp,open\n2026-07-16 00:00:00,1\n2026-07-16 00:15:00,2\n", encoding="utf-8")
    (tmp_path / "ETH_15m.csv").write_text("timestamp,open\n2026-07-16 00:00:00,1\n", encoding="utf-8")
    assert common_cutoff(tmp_path, ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]) == 1784160000000


def test_default_staging_output_has_one_canonical_location():
    assert DEFAULT_STAGING_OUT == Path("reports/staging_cohort_c/prospective_cohort_c_short_exploration_ledger.json")


def test_streaming_reader_matches_frozen_full_algorithm_on_triggering_history(tmp_path):
    path = tmp_path / "BTC_15m.csv"
    start = datetime(2026, 6, 20, tzinfo=timezone.utc)
    rows = ["timestamp,open,high,low,close,volume"]
    for day in range(26):
        for step in range(96):
            timestamp = start + timedelta(days=day, minutes=15 * step)
            high, low, close = 101.0, 99.0, 100.0
            if day == 25 and 80 <= step < 84:
                high, low = 300.0, 80.0
            rows.append(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')},100,{high},{low},{close},1")
    rows.append("2026-07-16 00:00:00,100,101,99,100,1")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    cutoff = common_cutoff(tmp_path, ["BTC-USDT-SWAP"])
    full = signals_for_symbol("BTC-USDT-SWAP", load_quantify_15m_csv(path), cutoff)
    streamed = signals_for_path("BTC-USDT-SWAP", path, cutoff)
    assert streamed == full
    assert len(streamed) == 1
    assert streamed[0]["signal_ts"] == ACTIVATION_TS
