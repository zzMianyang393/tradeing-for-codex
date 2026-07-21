from data_quality_audit import actual_common_cutoff


def test_actual_common_cutoff_uses_oldest_latest_bar_not_a_ledger_snapshot():
    cutoff, text = actual_common_cutoff([{"last_ts": 1_800_000}, {"last_ts": 900_000}])
    assert cutoff == 900_000
    assert text == "1970-01-01 00:15:00"
