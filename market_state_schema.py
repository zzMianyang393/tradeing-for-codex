from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Union

# ---------------------------------------------------------------------------
# Centralised Validation Allowed Values (Enums)
# ---------------------------------------------------------------------------
VALID_DIRECTIONS = {"uptrend", "downtrend", "range", "transition", "unknown"}
VALID_TREND_STAGES = {"early", "mature", "exhaustion", "unknown"}
VALID_VOLATILITY_STATES = {"compressed", "normal", "expanding", "extreme", "unknown"}
VALID_RISK_CYCLES = {"normal", "high_risk", "low_risk", "unknown"}
VALID_STRUCTURES = {"breakout", "breakdown", "pullback", "range", "unknown"}
VALID_TRADABLE_REGIMES = {"trend_following", "mean_reversion", "no_trade", "unknown"}
VALID_BREAKOUT_OR_PULLBACKS = {"breakout", "pullback", "range", "none", "unknown"}
VALID_ENTRY_CONTEXTS = {"oversold", "overbought", "breakout_test", "consolidation", "unknown"}
VALID_MOMENTUMS = {"strong_bullish", "weak_bullish", "flat", "weak_bearish", "strong_bearish", "unknown"}
VALID_LOCAL_STRUCTURES = {"higher_high", "lower_low", "range_bound", "unknown"}
VALID_LIQUIDITY_STATES = {"normal", "thin", "unknown"}
VALID_ALT_RELATIVE_STRENGTHS = {"broad", "BTC-led", "alt-led", "fragmented", "unknown"}


def ensure_utc(dt: datetime | str) -> datetime:
    """Ensures a datetime object or ISO string has explicit UTC timezone info.
    
    Raises ValueError for naive datetimes or strings missing explicit Z or offset.
    """
    if isinstance(dt, str):
        orig_str = dt
        # Check if the string has Z suffix or an offset like +00:00 / -05:00
        has_z = orig_str.endswith("Z")
        has_offset = ("+" in orig_str or ("-" in orig_str and len(orig_str.split("-")) > 3))
        
        if not (has_z or has_offset):
            raise ValueError(
                f"Implicit timezone rejected: '{orig_str}' must end with 'Z' or a valid UTC offset."
            )
            
        if has_z:
            dt = dt[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(dt)
        except ValueError as e:
            raise ValueError(f"Invalid ISO datetime string: {orig_str}") from e
            
        if parsed.tzinfo is None:
            raise ValueError(
                f"Implicit timezone rejected: '{orig_str}' has no timezone offset."
            )
        return parsed.astimezone(timezone.utc)
        
    elif isinstance(dt, datetime):
        if dt.tzinfo is None:
            raise ValueError("Implicit timezone rejected: naive datetime objects are not allowed.")
        return dt.astimezone(timezone.utc)
        
    raise TypeError(f"Expected datetime or ISO string, got {type(dt)}")


@dataclass
class TimeframeState:
    timeframe: str


@dataclass
class WeeklyState(TimeframeState):
    direction: str = "unknown"
    trend_strength: Union[float, str] = "unknown"
    volatility_state: str = "unknown"
    risk_cycle: str = "unknown"

    def __post_init__(self) -> None:
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid Weekly direction: '{self.direction}'")
        if self.volatility_state not in VALID_VOLATILITY_STATES:
            raise ValueError(f"Invalid Weekly volatility_state: '{self.volatility_state}'")
        if self.risk_cycle not in VALID_RISK_CYCLES:
            raise ValueError(f"Invalid Weekly risk_cycle: '{self.risk_cycle}'")
        if not isinstance(self.trend_strength, (int, float)):
            if self.trend_strength != "unknown":
                raise ValueError(f"Invalid Weekly trend_strength: '{self.trend_strength}'")

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "direction": self.direction,
            "trend_strength": self.trend_strength,
            "volatility_state": self.volatility_state,
            "risk_cycle": self.risk_cycle,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WeeklyState:
        return cls(
            timeframe=data.get("timeframe", "1w"),
            direction=data.get("direction", "unknown"),
            trend_strength=data.get("trend_strength", "unknown"),
            volatility_state=data.get("volatility_state", "unknown"),
            risk_cycle=data.get("risk_cycle", "unknown"),
        )


@dataclass
class DailyState(TimeframeState):
    direction: str = "unknown"
    trend_stage: str = "unknown"
    volatility_state: str = "unknown"
    structure: str = "unknown"

    def __post_init__(self) -> None:
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid Daily direction: '{self.direction}'")
        if self.trend_stage not in VALID_TREND_STAGES:
            raise ValueError(f"Invalid Daily trend_stage: '{self.trend_stage}'")
        if self.volatility_state not in VALID_VOLATILITY_STATES:
            raise ValueError(f"Invalid Daily volatility_state: '{self.volatility_state}'")
        if self.structure not in VALID_STRUCTURES:
            raise ValueError(f"Invalid Daily structure: '{self.structure}'")

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "direction": self.direction,
            "trend_stage": self.trend_stage,
            "volatility_state": self.volatility_state,
            "structure": self.structure,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DailyState:
        return cls(
            timeframe=data.get("timeframe", "1d"),
            direction=data.get("direction", "unknown"),
            trend_stage=data.get("trend_stage", "unknown"),
            volatility_state=data.get("volatility_state", "unknown"),
            structure=data.get("structure", "unknown"),
        )


@dataclass
class H4State(TimeframeState):
    direction: str = "unknown"
    tradable_regime: str = "unknown"
    trend_stage: str = "unknown"
    breakout_or_pullback: str = "unknown"
    volatility_state: str = "unknown"

    def __post_init__(self) -> None:
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid H4 direction: '{self.direction}'")
        if self.tradable_regime not in VALID_TRADABLE_REGIMES:
            raise ValueError(f"Invalid H4 tradable_regime: '{self.tradable_regime}'")
        if self.trend_stage not in VALID_TREND_STAGES:
            raise ValueError(f"Invalid H4 trend_stage: '{self.trend_stage}'")
        if self.breakout_or_pullback not in VALID_BREAKOUT_OR_PULLBACKS:
            raise ValueError(f"Invalid H4 breakout_or_pullback: '{self.breakout_or_pullback}'")
        if self.volatility_state not in VALID_VOLATILITY_STATES:
            raise ValueError(f"Invalid H4 volatility_state: '{self.volatility_state}'")

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "direction": self.direction,
            "tradable_regime": self.tradable_regime,
            "trend_stage": self.trend_stage,
            "breakout_or_pullback": self.breakout_or_pullback,
            "volatility_state": self.volatility_state,
        }

    @classmethod
    def from_dict(cls, data: dict) -> H4State:
        # Default direction to "unknown" if missing in old JSON format (backward compatibility)
        return cls(
            timeframe=data.get("timeframe", "4h"),
            direction=data.get("direction", "unknown"),
            tradable_regime=data.get("tradable_regime", "unknown"),
            trend_stage=data.get("trend_stage", "unknown"),
            breakout_or_pullback=data.get("breakout_or_pullback", "unknown"),
            volatility_state=data.get("volatility_state", "unknown"),
        )


@dataclass
class M15State(TimeframeState):
    entry_context: str = "unknown"
    momentum: str = "unknown"
    local_structure: str = "unknown"
    liquidity_state: str = "unknown"

    def __post_init__(self) -> None:
        if self.entry_context not in VALID_ENTRY_CONTEXTS:
            raise ValueError(f"Invalid M15 entry_context: '{self.entry_context}'")
        if self.momentum not in VALID_MOMENTUMS:
            raise ValueError(f"Invalid M15 momentum: '{self.momentum}'")
        if self.local_structure not in VALID_LOCAL_STRUCTURES:
            raise ValueError(f"Invalid M15 local_structure: '{self.local_structure}'")
        if self.liquidity_state not in VALID_LIQUIDITY_STATES:
            raise ValueError(f"Invalid M15 liquidity_state: '{self.liquidity_state}'")

    def to_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "entry_context": self.entry_context,
            "momentum": self.momentum,
            "local_structure": self.local_structure,
            "liquidity_state": self.liquidity_state,
        }

    @classmethod
    def from_dict(cls, data: dict) -> M15State:
        return cls(
            timeframe=data.get("timeframe", "15m"),
            entry_context=data.get("entry_context", "unknown"),
            momentum=data.get("momentum", "unknown"),
            local_structure=data.get("local_structure", "unknown"),
            liquidity_state=data.get("liquidity_state", "unknown"),
        )


@dataclass
class MarketRegimeState:
    btc_state: str = "unknown"
    eth_state: str = "unknown"
    market_breadth: Union[float, str] = "unknown"
    alt_relative_strength: str = "unknown"
    cross_section_dispersion: Union[float, str] = "unknown"

    def __post_init__(self) -> None:
        if self.btc_state not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid MarketRegime btc_state: '{self.btc_state}'")
        if self.eth_state not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid MarketRegime eth_state: '{self.eth_state}'")
        if self.alt_relative_strength not in VALID_ALT_RELATIVE_STRENGTHS:
            raise ValueError(f"Invalid MarketRegime alt_relative_strength: '{self.alt_relative_strength}'")
        if not isinstance(self.market_breadth, (int, float)):
            if self.market_breadth != "unknown":
                raise ValueError(f"Invalid MarketRegime market_breadth: '{self.market_breadth}'")
        if not isinstance(self.cross_section_dispersion, (int, float)):
            if self.cross_section_dispersion != "unknown":
                raise ValueError(f"Invalid MarketRegime cross_section_dispersion: '{self.cross_section_dispersion}'")

    def to_dict(self) -> dict:
        return {
            "btc_state": self.btc_state,
            "eth_state": self.eth_state,
            "market_breadth": self.market_breadth,
            "alt_relative_strength": self.alt_relative_strength,
            "cross_section_dispersion": self.cross_section_dispersion,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MarketRegimeState:
        return cls(
            btc_state=data.get("btc_state", "unknown"),
            eth_state=data.get("eth_state", "unknown"),
            market_breadth=data.get("market_breadth", "unknown"),
            alt_relative_strength=data.get("alt_relative_strength", "unknown"),
            cross_section_dispersion=data.get("cross_section_dispersion", "unknown"),
        )


@dataclass
class StateConflict:
    timeframe_a: str
    timeframe_b: str
    field: str
    value_a: Any
    value_b: Any
    severity: str
    description: str

    def to_dict(self) -> dict:
        return {
            "timeframe_a": self.timeframe_a,
            "timeframe_b": self.timeframe_b,
            "field": self.field,
            "value_a": self.value_a,
            "value_b": self.value_b,
            "severity": self.severity,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StateConflict:
        return cls(
            timeframe_a=data["timeframe_a"],
            timeframe_b=data["timeframe_b"],
            field=data["field"],
            value_a=data["value_a"],
            value_b=data["value_b"],
            severity=data.get("severity", "medium"),
            description=data.get("description", ""),
        )


@dataclass
class MarketStateConfig:
    version: str = "v1.1.0"
    min_bars_required: dict[str, int] = field(
        default_factory=lambda: {
            "1w": 50,
            "1d": 200,
            "4h": 200,
            "15m": 30,
        }
    )
    trend_strength_threshold: float = 1.5
    volatility_compressed_percentile: float = 20.0
    volatility_expanding_percentile: float = 80.0
    volatility_extreme_percentile: float = 95.0
    conflict_rules: dict[str, str] = field(
        default_factory=lambda: {
            "weekly_vs_daily_direction": "high",
            "daily_vs_h4_direction": "medium",
            "h4_vs_m15_direction": "medium",
            "weekly_vs_h4_volatility": "medium",
        }
    )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "min_bars_required": self.min_bars_required,
            "trend_strength_threshold": self.trend_strength_threshold,
            "volatility_compressed_percentile": self.volatility_compressed_percentile,
            "volatility_expanding_percentile": self.volatility_expanding_percentile,
            "volatility_extreme_percentile": self.volatility_extreme_percentile,
            "conflict_rules": self.conflict_rules,
        }

    def fingerprint(self) -> str:
        """Deterministic SHA-256 fingerprint of the configuration."""
        data = self.to_dict()
        blob = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    @classmethod
    def from_dict(cls, data: dict) -> MarketStateConfig:
        return cls(
            version=data.get("version", "v1.1.0"),
            min_bars_required=data.get("min_bars_required", {"1w": 50, "1d": 200, "4h": 200, "15m": 30}),
            trend_strength_threshold=data.get("trend_strength_threshold", 1.5),
            volatility_compressed_percentile=data.get("volatility_compressed_percentile", 20.0),
            volatility_expanding_percentile=data.get("volatility_expanding_percentile", 80.0),
            volatility_extreme_percentile=data.get("volatility_extreme_percentile", 95.0),
            conflict_rules=data.get("conflict_rules", {}),
        )


@dataclass
class MarketState:
    weekly: WeeklyState
    daily: DailyState
    h4: H4State
    m15: M15State
    market_regime: MarketRegimeState
    available_at: datetime
    source_bar_close_time: datetime
    confidence: float
    state_started_at: datetime
    version: str
    insufficient_data_reasons: list[str] = field(default_factory=list)
    conflicts: list[StateConflict] = field(default_factory=list)
    is_consistent: bool = True

    def __post_init__(self) -> None:
        self.available_at = ensure_utc(self.available_at)
        self.source_bar_close_time = ensure_utc(self.source_bar_close_time)
        self.state_started_at = ensure_utc(self.state_started_at)

        # Enforce bounds on confidence
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence score must be between 0.0 and 1.0, got {self.confidence}")

        # Enforce relationship constraints
        if self.source_bar_close_time > self.available_at:
            raise ValueError(
                f"Future leakage: source_bar_close_time ({self.source_bar_close_time}) "
                f"cannot be after available_at ({self.available_at})."
            )
        if self.state_started_at > self.available_at:
            raise ValueError(
                f"state_started_at ({self.state_started_at}) cannot be after available_at ({self.available_at})."
            )

    def to_dict(self) -> dict:
        return {
            "weekly": self.weekly.to_dict(),
            "daily": self.daily.to_dict(),
            "h4": self.h4.to_dict(),
            "m15": self.m15.to_dict(),
            "market_regime": self.market_regime.to_dict(),
            "available_at": self.available_at.isoformat().replace("+00:00", "Z"),
            "source_bar_close_time": self.source_bar_close_time.isoformat().replace("+00:00", "Z"),
            "confidence": self.confidence,
            "state_started_at": self.state_started_at.isoformat().replace("+00:00", "Z"),
            "version": self.version,
            "insufficient_data_reasons": self.insufficient_data_reasons,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "is_consistent": self.is_consistent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MarketState:
        return cls(
            weekly=WeeklyState.from_dict(data["weekly"]),
            daily=DailyState.from_dict(data["daily"]),
            h4=H4State.from_dict(data["h4"]),
            m15=M15State.from_dict(data["m15"]),
            market_regime=MarketRegimeState.from_dict(data["market_regime"]),
            available_at=ensure_utc(data["available_at"]),
            source_bar_close_time=ensure_utc(data["source_bar_close_time"]),
            confidence=data.get("confidence", 1.0),
            state_started_at=ensure_utc(data["state_started_at"]),
            version=data.get("version", "v1.0.0"),
            insufficient_data_reasons=data.get("insufficient_data_reasons", []),
            conflicts=[StateConflict.from_dict(c) for c in data.get("conflicts", [])],
            is_consistent=data.get("is_consistent", True),
        )


@dataclass
class MarketStateSnapshot:
    snapshot_id: str
    timestamp: datetime
    symbol: str
    state: MarketState
    version: str

    def __post_init__(self) -> None:
        self.timestamp = ensure_utc(self.timestamp)
        if self.timestamp != self.state.available_at:
            raise ValueError(
                f"Snapshot timestamp ({self.timestamp}) must match state.available_at ({self.state.available_at})."
            )

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "symbol": self.symbol,
            "state": self.state.to_dict(),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MarketStateSnapshot:
        return cls(
            snapshot_id=data["snapshot_id"],
            timestamp=ensure_utc(data["timestamp"]),
            symbol=data["symbol"],
            state=MarketState.from_dict(data["state"]),
            version=data.get("version", "v1.0.0"),
        )


@dataclass
class MarketStateTransition:
    transition_id: str
    symbol: str
    previous_state: Optional[MarketState]
    current_state: MarketState
    transition_time: datetime
    changed_fields: list[str]
    trigger_event: str
    version: str

    def __post_init__(self) -> None:
        self.transition_time = ensure_utc(self.transition_time)
        if self.transition_time < self.current_state.available_at:
            raise ValueError(
                f"Transition time ({self.transition_time}) cannot be before current_state.available_at ({self.current_state.available_at})."
            )

    def to_dict(self) -> dict:
        return {
            "transition_id": self.transition_id,
            "symbol": self.symbol,
            "previous_state": self.previous_state.to_dict() if self.previous_state else None,
            "current_state": self.current_state.to_dict(),
            "transition_time": self.transition_time.isoformat().replace("+00:00", "Z"),
            "changed_fields": self.changed_fields,
            "trigger_event": self.trigger_event,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MarketStateTransition:
        prev = data.get("previous_state")
        return cls(
            transition_id=data["transition_id"],
            symbol=data["symbol"],
            previous_state=MarketState.from_dict(prev) if prev else None,
            current_state=MarketState.from_dict(data["current_state"]),
            transition_time=ensure_utc(data["transition_time"]),
            changed_fields=data.get("changed_fields", []),
            trigger_event=data.get("trigger_event", ""),
            version=data.get("version", "v1.0.0"),
        )


def generate_snapshot_id(
    symbol: str,
    available_at: datetime,
    config_fingerprint: str,
    state: MarketState,
) -> str:
    """Deterministic SHA-256 snapshot ID bound to symbol, available_at, config fingerprint, and state content."""
    utc_dt = ensure_utc(available_at)
    available_at_str = utc_dt.isoformat().replace("+00:00", "Z")
    
    payload = {
        "symbol": symbol,
        "available_at": available_at_str,
        "config_fingerprint": config_fingerprint,
        "weekly": state.weekly.to_dict(),
        "daily": state.daily.to_dict(),
        "h4": state.h4.to_dict(),
        "m15": state.m15.to_dict(),
        "market_regime": state.market_regime.to_dict(),
    }
    
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Stable Public Interfaces for external integrations (e.g. research_protocol)
# ---------------------------------------------------------------------------
def get_market_state_schema_version() -> str:
    """Returns the current stable schema version."""
    return "v1.1.0"


def get_market_state_config_fingerprint() -> str:
    """Returns the SHA-256 fingerprint of the default MarketStateConfig."""
    return MarketStateConfig().fingerprint()


def timeframe_state_from_dict(data: dict) -> WeeklyState | DailyState | H4State | M15State:
    timeframe = data.get("timeframe")
    if timeframe == "1w":
        return WeeklyState.from_dict(data)
    elif timeframe == "1d":
        return DailyState.from_dict(data)
    elif timeframe == "4h":
        return H4State.from_dict(data)
    elif timeframe == "15m":
        return M15State.from_dict(data)
    else:
        raise ValueError(f"Unknown timeframe identifier: {timeframe}")
