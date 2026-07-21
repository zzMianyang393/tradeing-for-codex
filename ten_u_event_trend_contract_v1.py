"""Frozen research contract for the 10U single-symbol event-trend candidate.

This module intentionally contains no market-data loader and no return
calculation.  It is the pre-performance contract that must be fingerprinted
before historical Formation data are evaluated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping


CONTRACT_VERSION = "v1.0.0"
STRATEGY_ID = "ten_u_single_symbol_event_trend_48h_v1"


def _utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("research boundaries must use an explicit UTC Z suffix")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.tzinfo != timezone.utc:
        raise ValueError("research boundaries must be UTC")
    return parsed


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class EventTrendResearchWindows:
    formation_start: str = "2025-12-15T16:00:00Z"
    formation_end: str = "2026-04-01T00:00:00Z"
    retrospective_validation_start: str = "2026-04-01T00:00:00Z"
    retrospective_validation_end: str = "2026-05-16T00:00:00Z"
    contaminated_case_start: str = "2026-05-16T00:00:00Z"
    contaminated_case_end: str = "2026-07-16T00:00:00Z"
    prospective_oos_start: str = "2026-07-16T00:00:00Z"

    def __post_init__(self) -> None:
        ordered = [
            _utc(self.formation_start),
            _utc(self.formation_end),
            _utc(self.retrospective_validation_start),
            _utc(self.retrospective_validation_end),
            _utc(self.contaminated_case_start),
            _utc(self.contaminated_case_end),
            _utc(self.prospective_oos_start),
        ]
        if ordered != sorted(ordered):
            raise ValueError("research windows must be chronological")
        if self.formation_end != self.retrospective_validation_start:
            raise ValueError("Formation and retrospective validation must be adjacent")
        if self.retrospective_validation_end != self.contaminated_case_start:
            raise ValueError("validation must end where the contaminated case window begins")
        if self.contaminated_case_end != self.prospective_oos_start:
            raise ValueError("prospective OOS must start after the contaminated case window")

    def classify(self, timestamp: str) -> str:
        current = _utc(timestamp)
        if _utc(self.formation_start) <= current < _utc(self.formation_end):
            return "formation"
        if _utc(self.retrospective_validation_start) <= current < _utc(
            self.retrospective_validation_end
        ):
            return "retrospective_validation"
        if _utc(self.contaminated_case_start) <= current < _utc(self.contaminated_case_end):
            return "contaminated_case_only"
        if current >= _utc(self.prospective_oos_start):
            return "prospective_oos"
        return "pre_research"


@dataclass(frozen=True)
class EventTrendConfig:
    strategy_id: str = STRATEGY_ID
    contract_version: str = CONTRACT_VERSION
    symbols: tuple[str, ...] = (
        "RAVE-USDT-SWAP",
        "LAB-USDT-SWAP",
        "ETH-USDT-SWAP",
    )
    signal_bar: str = "1H"
    ignition_bar: str = "4H"
    maximum_concurrent_positions: int = 1
    maximum_holding_hours: int = 48
    minimum_holding_before_trailing_hours: int = 12

    # Four-hour ignition.  Both baselines exclude the trigger bar.
    baseline_4h_bars: int = 20
    true_range_median_multiple: Decimal = Decimal("2.0")
    quote_volume_median_multiple: Decimal = Decimal("2.0")
    close_location_long_min: Decimal = Decimal("0.75")
    close_location_short_max: Decimal = Decimal("0.25")
    prior_range_break_4h_bars: int = 20

    # First pullback and causal resumption on completed one-hour bars.
    pullback_wait_hours: int = 12
    require_counter_direction_close: bool = True
    cancel_if_close_crosses_ignition_midpoint: bool = True
    resumption_rule: str = "close_beyond_previous_1h_extreme_then_next_open"

    # Stop design: close-based structural invalidation plus a remote hard stop.
    atr_1h_period: int = 14
    atr_method: str = "wilder_seed_sma_then_recursive"
    disaster_stop_buffer_atr: Decimal = Decimal("0.5")
    maximum_disaster_stop_distance: Decimal = Decimal("0.20")
    structural_exit_confirmation_closes: int = 1
    trailing_rule_after_12h: str = "completed_4h_close_beyond_previous_4h_extreme"
    fixed_take_profit: bool = False
    same_timestamp_arbitration: str = "min_tr_volume_ratio_desc_then_symbol"
    signals_during_open_position: str = "discard"

    # Isolated 10U account. Actual notional is risk/stop-distance sized.
    initial_equity: Decimal = Decimal("10")
    risk_per_trade: Decimal = Decimal("0.15")
    maximum_effective_leverage: Decimal = Decimal("3.0")
    taker_fee_each_side: Decimal = Decimal("0.0005")
    slippage_each_side: Decimal = Decimal("0.0002")
    funding_cost_status: str = "actual_history_required"
    consecutive_loss_cooldown_trades: int = 3
    cooldown_hours: int = 24
    daily_loss_halt: Decimal = Decimal("0.35")
    peak_drawdown_halt: Decimal = Decimal("0.70")
    ruin_equity: Decimal = Decimal("2.0")
    post_stop_recovery_observation_hours: int = 12

    # A primary failure cannot be rescued by a sensitivity variant.
    sensitivity_variants: Mapping[str, Mapping[str, str]] = field(
        default_factory=lambda: {
            "higher_ignition_threshold": {
                "true_range_median_multiple": "2.2",
                "quote_volume_median_multiple": "2.2",
            },
            "longer_pullback_wait": {"pullback_wait_hours": "16"},
        }
    )

    def __post_init__(self) -> None:
        if not 1 <= len(self.symbols) <= 3 or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("the event-trend universe must contain one to three unique symbols")
        if self.maximum_concurrent_positions != 1:
            raise ValueError("the 10U event-trend account permits one open position")
        if self.maximum_holding_hours not in (24, 48):
            raise ValueError("the frozen holding horizon must be one or two days")
        if self.minimum_holding_before_trailing_hours >= self.maximum_holding_hours:
            raise ValueError("trailing protection must start before the time exit")
        if self.funding_cost_status != "actual_history_required":
            raise ValueError("a 24-48h perpetual strategy must apply actual funding history")
        if self.maximum_effective_leverage > Decimal("3.0"):
            raise ValueError("v1 caps effective leverage at 3x to preserve hard-stop distance")
        if not Decimal("0") < self.risk_per_trade < Decimal("1"):
            raise ValueError("risk_per_trade must be between zero and one")
        if not Decimal("0") < self.maximum_disaster_stop_distance < Decimal("1"):
            raise ValueError("maximum disaster-stop distance must be a price fraction")
        if self.same_timestamp_arbitration != "min_tr_volume_ratio_desc_then_symbol":
            raise ValueError("v1 arbitration is frozen")
        if self.signals_during_open_position != "discard":
            raise ValueError("v1 does not queue stale event signals")
        if self.atr_method != "wilder_seed_sma_then_recursive":
            raise ValueError("v1 ATR method is frozen")
        frozen_variants = {
            name: MappingProxyType(dict(values))
            for name, values in sorted(self.sensitivity_variants.items())
        }
        object.__setattr__(self, "sensitivity_variants", MappingProxyType(frozen_variants))

    def to_dict(self) -> dict[str, Any]:
        # ``asdict`` deep-copies values and therefore cannot serialize the
        # MappingProxyType used to make sensitivity variants genuinely
        # immutable.  Read each frozen field without copying instead.
        return _jsonable({item.name: getattr(self, item.name) for item in fields(self)})

    def fingerprint(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EventTrendFormationGate:
    minimum_trades: int = 12
    minimum_rave_trades: int = 2
    minimum_lab_trades: int = 2
    minimum_profit_factor: Decimal = Decimal("1.25")
    minimum_ending_equity: Decimal = Decimal("10")
    minimum_peak_equity: Decimal = Decimal("15")
    maximum_drawdown_fraction: Decimal = Decimal("0.70")
    minimum_peak_profit_retention: Decimal = Decimal("0.50")
    maximum_stopped_then_recovered_fraction: Decimal = Decimal("0.35")
    minimum_median_winner_capture: Decimal = Decimal("0.35")
    maximum_top_trade_gross_profit_contribution: Decimal = Decimal("0.50")
    primary_must_pass: bool = True
    sensitivity_cannot_rescue_primary: bool = True

    def __post_init__(self) -> None:
        if self.minimum_trades < 1:
            raise ValueError("minimum_trades must be positive")
        for name in (
            "maximum_drawdown_fraction",
            "minimum_peak_profit_retention",
            "maximum_stopped_then_recovered_fraction",
            "minimum_median_winner_capture",
            "maximum_top_trade_gross_profit_contribution",
        ):
            value = getattr(self, name)
            if not Decimal("0") <= value <= Decimal("1"):
                raise ValueError(f"{name} must be between zero and one")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def fingerprint(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


def build_preregistration() -> dict[str, Any]:
    config = EventTrendConfig()
    windows = EventTrendResearchWindows()
    gate = EventTrendFormationGate()
    return {
        "strategy_id": STRATEGY_ID,
        "contract_version": CONTRACT_VERSION,
        "formal_status": "preregistered_before_formation_performance",
        "config": config.to_dict(),
        "config_fingerprint": config.fingerprint(),
        "formation_gate": gate.to_dict(),
        "formation_gate_fingerprint": gate.fingerprint(),
        "windows": asdict(windows),
        "contamination_policy": {
            "reason": "the 2026-05-16 through 2026-07-15 RAVE/LAB/ETH paths were inspected before this contract",
            "performance_use": "descriptive_case_only",
            "may_validate": False,
            "may_count_as_oos": False,
        },
        "phase_unlock": {
            "formation": True,
            "retrospective_validation": False,
            "prospective_oos": False,
        },
        "anti_overfit": {
            "parameter_search_allowed": False,
            "primary_failure_action": "reject_candidate",
            "sensitivity_variant_selection_allowed": False,
            "validation_unlock_requires_formation_pass": True,
            "prospective_oos_metrics_before_maturity": False,
        },
    }


if __name__ == "__main__":
    print(json.dumps(build_preregistration(), indent=2))
