from ten_u_event_trend_data_v1 import FullHourlyCandle, format_utc
from prod.ten_u_market_refresh import (
    floor_hour_ms,
    merge_hourly_candles,
    next_refresh_window,
)


def _c(ts: int) -> FullHourlyCandle:
    return FullHourlyCandle(
        timestamp_ms=ts,
        timestamp_utc=format_utc(ts),
        open="1",
        high="2",
        low="0.5",
        close="1.5",
        volume_contracts="1",
        volume_base="1",
        volume_quote="1",
        confirmed=True,
    )


def test_floor_hour():
    assert floor_hour_ms(3_600_000 + 5) == 3_600_000


def test_next_refresh_window_empty_and_catchup():
    now = 10 * 3_600_000
    start, end = next_refresh_window([], now_ms=now, max_lookback_hours=2)
    assert end == now
    assert start == now - 2 * 3_600_000

    existing = [_c(7 * 3_600_000)]
    start, end = next_refresh_window(existing, now_ms=now, max_lookback_hours=72)
    assert start == 8 * 3_600_000
    assert end == now


def test_merge_hourly_no_rewrite():
    a = _c(0)
    b = _c(3_600_000)
    merged = merge_hourly_candles([a], [b, a])
    assert [c.timestamp_ms for c in merged] == [0, 3_600_000]


def test_merge_hourly_refuses_rewrite():
    a = _c(0)
    bad = FullHourlyCandle(
        timestamp_ms=0,
        timestamp_utc=format_utc(0),
        open="9",
        high="9",
        low="9",
        close="9",
        volume_contracts="1",
        volume_base="1",
        volume_quote="1",
        confirmed=True,
    )
    try:
        merge_hourly_candles([a], [bad])
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "rewrite" in str(exc)
