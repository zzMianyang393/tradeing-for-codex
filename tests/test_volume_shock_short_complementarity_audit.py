from volume_shock_short_complementarity_audit import filter_common_window


def test_filter_common_window_requires_symbol_entry_and_exit_coverage():
    events = [
        {"symbol": "BTC", "entry_ts": 10, "exit_ts": 20},
        {"symbol": "ETH", "entry_ts": 10, "exit_ts": 20},
        {"symbol": "BTC", "entry_ts": 5, "exit_ts": 20},
        {"symbol": "BTC", "entry_ts": 10, "exit_ts": 30},
    ]
    assert filter_common_window(events, {"BTC"}, 10, 20) == [events[0]]
