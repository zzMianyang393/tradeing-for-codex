from daily_failed_breakout_reversal_audit import BREAKOUT_ATR, STOP_ATR, WICK_MINIMUM, short_event
from market import Bar


def test_card_constants_are_frozen():
    assert (BREAKOUT_ATR, WICK_MINIMUM, STOP_ATR) == (0.25, 0.40, 1.5)


def test_short_event_uses_one_point_five_atr_stop():
    bars = [
        Bar(0, "1970-01-01 00:00:00", 100.0, 100.0, 100.0, 100.0, 1.0),
        Bar(900_000, "1970-01-01 00:15:00", 100.0, 101.6, 99.0, 100.0, 1.0),
        Bar(5 * 24 * 3600 * 1000, "1970-01-06 00:00:00", 100.0, 100.0, 100.0, 100.0, 1.0),
    ]
    event = short_event("BTC-USDT-SWAP", 0, bars, 1.0, "test")
    assert event is not None
    assert event["stop_price"] == 101.5
    assert event["exit_reason"] == "stop"
