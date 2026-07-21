"""Frozen successor contract: persistence-confirmed 10U event trends."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
from typing import Any

from ten_u_event_trend_contract_v1 import EventTrendConfig, _jsonable, _utc


CONTRACT_VERSION = "v2.0.0"
STRATEGY_ID = "ten_u_single_symbol_persistent_event_trend_48h_v2"


@dataclass(frozen=True)
class PersistentEventTrendWindows:
    development_contaminated_start: str = "2025-12-15T16:00:00Z"
    development_contaminated_end: str = "2026-04-01T00:00:00Z"
    sealed_screen_start: str = "2026-04-01T00:00:00Z"
    sealed_screen_end: str = "2026-05-16T00:00:00Z"
    case_contaminated_start: str = "2026-05-16T00:00:00Z"
    case_contaminated_end: str = "2026-07-16T00:00:00Z"
    prospective_start: str = "2026-07-16T00:00:00Z"
    prospective_minimum_days: int = 90
    prospective_minimum_trades: int = 6

    def __post_init__(self) -> None:
        boundaries = [
            _utc(self.development_contaminated_start),
            _utc(self.development_contaminated_end),
            _utc(self.sealed_screen_start),
            _utc(self.sealed_screen_end),
            _utc(self.case_contaminated_start),
            _utc(self.case_contaminated_end),
            _utc(self.prospective_start),
        ]
        if boundaries != sorted(boundaries):
            raise ValueError("v2 windows must be chronological")
        if self.development_contaminated_end != self.sealed_screen_start:
            raise ValueError("sealed screen must follow the v1 development interval")
        if self.sealed_screen_end != self.case_contaminated_start:
            raise ValueError("sealed screen must end before the inspected case interval")
        if self.case_contaminated_end != self.prospective_start:
            raise ValueError("prospective observation starts after all inspected cases")


@dataclass(frozen=True)
class PersistentEventTrendConfig:
    strategy_id: str = STRATEGY_ID
    contract_version: str = CONTRACT_VERSION
    symbols: tuple[str, ...] = (
        "RAVE-USDT-SWAP",
        "LAB-USDT-SWAP",
        "ETH-USDT-SWAP",
    )
    base_ignition_contract_fingerprint: str = EventTrendConfig().fingerprint()
    base_true_range_multiple: Decimal = Decimal("2.0")
    base_quote_volume_multiple: Decimal = Decimal("2.0")
    persistence_completed_4h_bars: int = 3
    persistence_rule: str = "all_closes_hold_midpoint_and_final_close_breaks_ignition_extreme"
    post_confirmation_pullback_wait_hours: int = 8
    entry_rule: str = "counter_close_then_close_beyond_previous_1h_extreme_then_next_open"
    cancellation_rule: str = "completed_1h_close_crosses_ignition_midpoint"
    atr_period_1h: int = 14
    atr_method: str = "wilder_seed_sma_then_recursive"
    disaster_stop_buffer_atr: Decimal = Decimal("0.5")
    maximum_disaster_stop_distance: Decimal = Decimal("0.20")
    maximum_holding_hours: int = 48
    trailing_starts_after_hours: int = 12
    trailing_rule: str = "completed_4h_close_beyond_previous_4h_extreme"
    fixed_take_profit: bool = False
    initial_equity: Decimal = Decimal("10")
    risk_per_trade: Decimal = Decimal("0.15")
    maximum_effective_leverage: Decimal = Decimal("3.0")
    taker_fee_each_side: Decimal = Decimal("0.0005")
    slippage_each_side: Decimal = Decimal("0.0002")
    actual_funding_required: bool = True
    maximum_concurrent_positions: int = 1
    signals_during_open_position: str = "discard"
    same_timestamp_arbitration: str = "min_tr_volume_ratio_desc_then_symbol_first_executable"
    consecutive_loss_cooldown_trades: int = 3
    cooldown_hours: int = 24
    daily_loss_halt: Decimal = Decimal("0.35")
    peak_drawdown_halt: Decimal = Decimal("0.70")
    ruin_equity: Decimal = Decimal("2.0")

    def __post_init__(self) -> None:
        if len(self.symbols) != 3 or len(set(self.symbols)) != 3:
            raise ValueError("v2 freezes exactly three research symbols")
        if self.persistence_completed_4h_bars != 3:
            raise ValueError("v2 direction confirmation is exactly twelve hours")
        if self.post_confirmation_pullback_wait_hours != 8:
            raise ValueError("v2 pullback wait is frozen without a grid")
        if self.maximum_concurrent_positions != 1:
            raise ValueError("v2 permits one open position")
        if not self.actual_funding_required:
            raise ValueError("actual funding is mandatory")
        if self.maximum_effective_leverage > Decimal("3"):
            raise ValueError("v2 effective leverage cannot exceed 3x")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True)
class PersistentEventTrendScreenGate:
    minimum_trades: int = 6
    minimum_rave_trades: int = 1
    minimum_lab_trades: int = 1
    minimum_profit_factor: Decimal = Decimal("1.25")
    minimum_ending_equity: Decimal = Decimal("10")
    maximum_drawdown_fraction: Decimal = Decimal("0.70")
    minimum_peak_profit_retention: Decimal = Decimal("0.50")
    maximum_stopped_then_recovered_fraction: Decimal = Decimal("0.35")
    minimum_median_winner_capture: Decimal = Decimal("0.35")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def build_preregistration_v2() -> dict[str, Any]:
    config = PersistentEventTrendConfig()
    gate = PersistentEventTrendScreenGate()
    windows = PersistentEventTrendWindows()
    return {
        "strategy_id": STRATEGY_ID,
        "contract_version": CONTRACT_VERSION,
        "formal_status": "preregistered_before_sealed_screen_access",
        "config": config.to_dict(),
        "config_fingerprint": config.fingerprint(),
        "screen_gate": gate.to_dict(),
        "screen_gate_fingerprint": gate.fingerprint(),
        "windows": asdict(windows),
        "phase_access": {
            "v1_development_interval": False,
            "sealed_screen": True,
            "case_contaminated": False,
            "prospective_outcomes": False,
        },
        "interpretation": {
            "sealed_screen_pass": "prospective_candidate_only_not_validated",
            "sealed_screen_insufficient_sample": "prospective_observation_allowed_but_no_edge_claim",
            "sealed_screen_fail": "reject_v2",
        },
        "anti_overfit": {
            "parameter_grid": False,
            "sensitivity_variants": False,
            "symbol_or_direction_removal_after_result": False,
            "case_window_may_validate": False,
            "prospective_maturity_requires_both_days_and_trades": True,
        },
    }


if __name__ == "__main__":
    print(json.dumps(build_preregistration_v2(), indent=2))

