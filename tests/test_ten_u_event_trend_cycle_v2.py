from ten_u_event_trend_cycle_v2 import SAFE_SIGNAL_FIELDS


def test_cycle_safe_signal_schema_has_no_outcome_fields():
    forbidden = {
        "exit_ts",
        "exit_price",
        "pnl",
        "net_pnl",
        "mfe",
        "mae",
        "winner",
        "equity",
    }
    assert not forbidden.intersection(SAFE_SIGNAL_FIELDS)
    assert set(SAFE_SIGNAL_FIELDS) == {
        "symbol",
        "direction",
        "entry_time",
        "structural_invalidation",
        "atr_1h",
        "record_hash",
    }
