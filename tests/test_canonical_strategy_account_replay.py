from pathlib import Path

from canonical_strategy_account_replay import compact, daily_replayability, load_cached_price_maps, load_daily_price_maps


def test_daily_event_ledger_is_replayable():
    report = {"report_type": "daily_example", "events": [{
        "symbol": "BTC-USDT-SWAP", "entry_ts": 1, "exit_ts": 2,
        "entry_price": 1.0, "exit_price": 2.0, "direction": "long", "split": "formation",
    }]}
    valid, reason, events = daily_replayability(report)
    assert valid is True
    assert reason == "daily_event_ledger_complete"
    assert len(events) == 1


def test_non_daily_event_ledger_is_not_claimed_as_daily_account_replay():
    valid, reason, _events = daily_replayability({"report_type": "ema_4h", "events": [{}]})
    assert valid is False
    assert reason == "not_daily_event_report"


def test_missing_event_fields_are_explained():
    valid, reason, _events = daily_replayability({"report_type": "daily_example", "events": [{"symbol": "BTC-USDT-SWAP"}]})
    assert valid is False
    assert reason.startswith("events_missing_required_fields:")


def test_compact_excludes_equity_curve_and_keeps_account_metrics():
    result = {
        "candidate_events": 2, "accepted_positions": 1, "capacity_rejected_events": 1,
        "initial_equity": 100.0, "final_equity": 110.0, "total_return_pct": 10.0,
        "max_drawdown_pct": 2.0, "realized_win_rate": 1.0, "max_concurrent_positions": 1,
        "capital_turnover": 0.2, "top_positive_month_share": 1.0,
        "equity_curve": [{"ts": 1, "equity": 100.0}, {"ts": 86_400_001, "equity": 110.0}],
    }
    compacted = compact(result)
    assert "equity_curve" not in compacted
    assert compacted["total_return_pct"] == 10.0


def test_streamed_price_map_aggregates_intraday_rows_to_daily_bar(tmp_path: Path):
    (tmp_path / "BTC_15m.csv").write_text(
        "timestamp_ms,open,high,low,close,volume\n"
        "1704067200000,10,12,9,11,2\n"
        "1704068100000,11,13,10,12,3\n",
        encoding="utf-8",
    )
    maps = load_daily_price_maps(tmp_path, [{"symbol": "BTC-USDT-SWAP"}])
    bar = next(iter(maps["BTC-USDT-SWAP"].values()))
    assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (10.0, 13.0, 9.0, 12.0, 5.0)


def test_cached_price_map_reconstructs_daily_bars(tmp_path: Path):
    cache = tmp_path / "cache.json"
    cache.write_text('{"BTC-USDT-SWAP":[{"ts":0,"timestamp_utc":"1970-01-01 00:00:00","open":1,"high":2,"low":0.5,"close":1.5,"volume":3}]}', encoding="utf-8")
    maps = load_cached_price_maps([{"symbol": "BTC-USDT-SWAP"}], cache)
    assert maps["BTC-USDT-SWAP"][0].close == 1.5
