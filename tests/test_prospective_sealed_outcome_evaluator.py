from datetime import datetime, timedelta, timezone
from pathlib import Path

from prospective_sealed_outcome_evaluator import _concentration, _distribution, build


def _observation(index: int) -> dict:
    return {"observation_id": f"id-{index}", "hypothesis_id": "factor", "signal_ts": 1_000 + index, "symbol": "BTC-USDT-SWAP", "direction": "long", "regime": "震荡", "maturity_ts": 2_000}


def test_unmatured_observations_never_read_market_outcomes(tmp_path):
    registry = {"observations": [_observation(1)]}
    maturity = {"as_of_ts": 1_500, "observations": [{"observation_id": "id-1", "status": "awaiting_maturity"}]}
    report = build(registry, maturity, {"integrity_status": "valid"}, Path(tmp_path))
    assert report["evaluation_status"] == "awaiting_maturity"
    assert report["outcomes_evaluated"] is False


def test_integrity_failure_blocks_evaluation_before_market_read(tmp_path):
    registry = {"observations": [_observation(1)]}
    maturity = {"as_of_ts": 3_000, "observations": [{"observation_id": "id-1", "status": "mature_awaiting_sealed_evaluation"}]}
    report = build(registry, maturity, {"integrity_status": "invalid"}, Path(tmp_path))
    assert report["evaluation_status"] == "blocked_integrity"
    assert report["outcomes_evaluated"] is False


def test_mature_but_sparse_observations_remain_unevaluated(tmp_path):
    registry = {"observations": [_observation(1)]}
    maturity = {"as_of_ts": 3_000, "observations": [{"observation_id": "id-1", "status": "mature_awaiting_sealed_evaluation"}]}
    report = build(registry, maturity, {"integrity_status": "valid"}, Path(tmp_path))
    assert report["evaluation_status"] == "insufficient_independent_evidence"
    assert report["outcomes_evaluated"] is False


def test_concentration_and_distribution_group_by_utc_signal_day():
    rows = [
        {"signal_ts": 1_784_160_000_000, "symbol": "BTC", "net_observation_pct": 1.0},
        {"signal_ts": 1_784_163_600_000, "symbol": "ETH", "net_observation_pct": 2.0},
        {"signal_ts": 1_784_246_400_000, "symbol": "BTC", "net_observation_pct": 1.0},
    ]
    assert _concentration(rows, "signal_day") == 0.75
    distribution = _distribution(rows, "signal_day")
    assert sorted(item["count"] for item in distribution.values()) == [1, 2]


def test_ready_mature_observations_use_frozen_4h_prices_and_friction(tmp_path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    day_offsets = [0, 1, 2, 31, 32] * 2
    symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"]
    observations, maturity_rows, csv_rows = [], [], {symbol: ["timestamp,open,high,low,close,volume"] for symbol in symbols}
    for index, day_offset in enumerate(day_offsets):
        signal_dt = start + timedelta(days=day_offset)
        signal_ts = int(signal_dt.timestamp() * 1000)
        symbol = symbols[index % len(symbols)]
        observation = {"observation_id": f"ready-{index}", "hypothesis_id": "factor-a", "signal_ts": signal_ts, "symbol": symbol, "direction": "long", "regime": "高波动转换", "maturity_ts": signal_ts + 90 * 86_400_000}
        observations.append(observation)
        maturity_rows.append({"observation_id": observation["observation_id"], "status": "mature_awaiting_sealed_evaluation"})
        entry_dt = signal_dt + timedelta(hours=4)
        exit_dt = entry_dt + timedelta(days=90)
        csv_rows[symbol].append(f"{entry_dt.strftime('%Y-%m-%d %H:%M:%S')},100,100,100,100,1")
        csv_rows[symbol].append(f"{exit_dt.strftime('%Y-%m-%d %H:%M:%S')},110,110,110,110,1")
    for symbol, rows in csv_rows.items():
        rows[1:] = sorted(rows[1:])
        (tmp_path / f"{symbol.split('-', 1)[0]}_15m.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    report = build(
        {"observations": observations},
        {"as_of_ts": int((start + timedelta(days=200)).timestamp() * 1000), "observations": maturity_rows},
        {"integrity_status": "valid"},
        tmp_path,
    )
    assert report["evaluation_status"] == "sealed_evaluation_completed_no_automatic_approval"
    assert report["outcomes_evaluated"] is True
    assert report["summary"]["mean_net_observation_pct"] == 9.84
    assert report["per_hypothesis"]["factor-a"]["observation_count"] == 10
    assert set(report["contribution_distribution"]) == {"signal_day", "signal_month", "symbol", "regime", "direction"}
