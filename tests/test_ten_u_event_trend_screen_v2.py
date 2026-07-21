import json
from dataclasses import replace
from pathlib import Path

from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig, PersistentEventTrendScreenGate
from ten_u_event_trend_data_v1 import HOUR_MS
from ten_u_event_trend_formation_v1 import HourBar
from ten_u_event_trend_screen_v2 import (
    PersistenceConfirmation,
    _screen_gate,
    build_v2_proposals,
    find_persistence_confirmations,
    next_entry_available_at,
    run_sealed_screen,
)


def _hourly_persistence_case(final_persistent_close: float = 112) -> list[HourBar]:
    bars = [HourBar(i * HOUR_MS, 100, 101, 99, 100, 1000) for i in range(120)]
    for i in range(80, 84):
        bars[i] = HourBar(i * HOUR_MS, 100, 110, 99, 109, 3000)
    for i in range(84, 88):
        bars[i] = HourBar(i * HOUR_MS, 109, 110, 108, 109.5, 1000)
    for i in range(88, 92):
        bars[i] = HourBar(i * HOUR_MS, 109.5, 111, 109, 110.5, 1000)
    for i in range(92, 96):
        bars[i] = HourBar(i * HOUR_MS, 110.5, max(112, final_persistent_close), 110, final_persistent_close, 1000)
    return bars


def test_screen_gate_never_calls_small_sample_a_pass():
    report = {
        "trades": 5,
        "trades_by_symbol": {"RAVE-USDT-SWAP": 2, "LAB-USDT-SWAP": 2},
        "profit_factor": 10,
        "ending_equity": 30,
        "max_drawdown_fraction": 0.1,
        "peak_profit_retention": 1,
        "stopped_then_recovered_fraction": 0,
        "median_winner_capture": 1,
    }
    status, reasons = _screen_gate(report, PersistentEventTrendScreenGate())
    assert status == "sealed_screen_insufficient_evidence"
    assert reasons == ["trades_below_minimum"]


def test_screen_gate_pass_is_prospective_only():
    report = {
        "trades": 6,
        "trades_by_symbol": {"RAVE-USDT-SWAP": 1, "LAB-USDT-SWAP": 1},
        "profit_factor": 2,
        "ending_equity": 15,
        "max_drawdown_fraction": 0.2,
        "peak_profit_retention": 0.8,
        "stopped_then_recovered_fraction": 0.2,
        "median_winner_capture": 0.5,
    }
    status, reasons = _screen_gate(report, PersistentEventTrendScreenGate())
    assert status == "sealed_screen_pass_prospective_only"
    assert not reasons


def test_v2_has_no_parameter_variants():
    assert "sensitivity" not in PersistentEventTrendConfig().to_dict()


def test_persistence_requires_all_three_closes_and_final_extreme_break():
    config = PersistentEventTrendConfig(symbols=("TEST-USDT-SWAP", "X-USDT-SWAP", "Y-USDT-SWAP"))
    confirmed = find_persistence_confirmations(
        "TEST-USDT-SWAP", _hourly_persistence_case(), config, 0, 120 * HOUR_MS
    )
    assert len(confirmed) == 1
    not_confirmed = find_persistence_confirmations(
        "TEST-USDT-SWAP", _hourly_persistence_case(109.5), config, 0, 120 * HOUR_MS
    )
    assert not not_confirmed


def test_v2_entry_occurs_next_open_after_counter_close_and_resumption():
    bars = [HourBar(i * HOUR_MS, 100, 101, 99, 100, 1000) for i in range(120)]
    bars[96] = HourBar(96 * HOUR_MS, 100, 101, 98, 99, 1000)
    bars[97] = HourBar(97 * HOUR_MS, 99, 103, 99, 102, 1000)
    confirmation = PersistenceConfirmation(
        "TEST-USDT-SWAP", "long", 84 * HOUR_MS, 96 * HOUR_MS, 90, 3
    )
    config = PersistentEventTrendConfig(symbols=("TEST-USDT-SWAP", "X-USDT-SWAP", "Y-USDT-SWAP"))
    proposals = build_v2_proposals(
        "TEST-USDT-SWAP", bars, [confirmation], config, 120 * HOUR_MS
    )
    assert len(proposals) == 1
    assert proposals[0].entry_ts == 98 * HOUR_MS


def test_prospective_proposal_is_visible_at_entry_open_without_future_bar():
    bars = [HourBar(i * HOUR_MS, 100, 101, 99, 100, 1000) for i in range(98)]
    bars[96] = HourBar(96 * HOUR_MS, 100, 101, 98, 99, 1000)
    bars[97] = HourBar(97 * HOUR_MS, 99, 103, 99, 102, 1000)
    confirmation = PersistenceConfirmation(
        "TEST-USDT-SWAP", "long", 84 * HOUR_MS, 96 * HOUR_MS, 90, 3
    )
    config = PersistentEventTrendConfig(
        symbols=("TEST-USDT-SWAP", "X-USDT-SWAP", "Y-USDT-SWAP")
    )
    assert not build_v2_proposals(
        "TEST-USDT-SWAP", bars, [confirmation], config, 98 * HOUR_MS
    )
    proposals = build_v2_proposals(
        "TEST-USDT-SWAP",
        bars,
        [confirmation],
        config,
        98 * HOUR_MS,
        allow_entry_at_end=True,
    )
    assert len(proposals) == 1
    assert proposals[0].entry_ts == 98 * HOUR_MS


def test_intrabar_hard_stop_cannot_release_capital_at_same_hour_open():
    trade = {"exit_ts": 100 * HOUR_MS, "exit_reason": "hard_disaster_stop"}
    assert next_entry_available_at(trade) == 101 * HOUR_MS


def test_known_open_exit_can_rotate_without_artificial_extra_hour():
    for reason in ("time_48h", "structural_close_invalidation", "four_hour_structure_trail"):
        trade = {"exit_ts": 100 * HOUR_MS, "exit_reason": reason}
        assert next_entry_available_at(trade) == 100 * HOUR_MS


def test_causal_reentry_fix_does_not_change_stored_historical_account():
    root = Path(__file__).resolve().parents[1]
    rerun = run_sealed_screen(
        root / "data/event_trend_v1",
        root / "reports/ten_u_event_trend_preregistration_v2.json",
        root / "data/event_trend_v1/hourly_dataset_manifest_v1.json",
    )
    stored = json.loads(
        (root / "reports/ten_u_event_trend_screen_v2.json").read_text(encoding="utf-8")
    )
    assert rerun["account"] == stored["account"]
