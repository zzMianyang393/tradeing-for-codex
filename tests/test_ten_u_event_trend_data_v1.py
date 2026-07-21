from pathlib import Path

from ten_u_event_trend_data_v1 import (
    HOUR_MS,
    FullHourlyCandle,
    collect_completed_hourly,
    load_hourly,
    validate_hourly,
    write_hourly,
)


def row(ts: int, confirm: str = "1", quote_volume: str = "1234") -> list[str]:
    return [str(ts), "10", "12", "9", "11", "100", "1000", quote_volume, confirm]


def test_okx_units_are_preserved_explicitly():
    candle = FullHourlyCandle.from_okx(row(HOUR_MS, quote_volume="9876"))
    assert candle.volume_contracts == "100"
    assert candle.volume_base == "1000"
    assert candle.volume_quote == "9876"


def test_collection_excludes_future_unconfirmed_and_is_causal():
    pages = {
        None: [row(5 * HOUR_MS, "0"), row(4 * HOUR_MS), row(3 * HOUR_MS)],
        3 * HOUR_MS: [row(2 * HOUR_MS), row(HOUR_MS)],
    }

    def fetcher(symbol, after, limit):
        return pages.get(after, [])

    candles = collect_completed_hourly(
        "TEST-USDT-SWAP", HOUR_MS, 5 * HOUR_MS, page_fetcher=fetcher, sleep_seconds=0
    )
    assert [c.timestamp_ms for c in candles] == [HOUR_MS, 2 * HOUR_MS, 3 * HOUR_MS, 4 * HOUR_MS]


def test_validation_rejects_hourly_gaps():
    candles = [
        FullHourlyCandle.from_okx(row(HOUR_MS)),
        FullHourlyCandle.from_okx(row(3 * HOUR_MS)),
    ]
    result = validate_hourly(candles)
    assert result["status"] == "FAIL"
    assert result["missing_hours"]


def test_round_trip_and_hash_are_deterministic(tmp_path: Path):
    candles = [FullHourlyCandle.from_okx(row(HOUR_MS))]
    path = tmp_path / "candles.csv"
    first = write_hourly(path, candles)
    assert load_hourly(path) == candles
    assert write_hourly(path, candles) == first

