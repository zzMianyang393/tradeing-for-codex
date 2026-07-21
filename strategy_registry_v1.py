"""Strategy Registry v1 — immutable strategy descriptors and read-only registry.

This module defines *what* strategies exist and *when* they are eligible to be
routed.  It does NOT implement trading signals, sizing, or order execution.

Responsibility boundary:
- Registry: describes strategies, validates descriptors, produces fingerprints.
- Router (strategy_router_v1): matches MarketState → eligible strategies.
- Signal provider: produces actual entry signals (NOT in this module).
- Risk/sleeve: manages position sizing and risk (NOT in this module).

Design constraints:
- StrategyDescriptor is frozen (immutable after creation).
- strategy_id + strategy_version must be unique in a registry.
- Only 'formation_eligible' and 'frozen' strategies can be routing candidates.
- No dynamic imports, no runtime code loading.
- No backtest results, PnL, or window-dependent logic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Valid enums
# ---------------------------------------------------------------------------
VALID_RESEARCH_STATUSES = frozenset({
    "prototype",
    "formation_eligible",
    "frozen",
    "rejected",
    "disabled",
})

VALID_DIRECTIONS = frozenset({1, -1})  # 1 = long, -1 = short

VALID_SLEEVE_TYPES = frozenset({
    "trend",
    "mean_reversion",
    "breakout",
    "momentum",
    "carry",
    "volatility",
    "composite",
})

VALID_FAMILIES = frozenset({
    "trend_following",
    "mean_reversion",
    "breakout",
    "momentum",
    "carry",
    "volatility",
    "funding",
    "open_interest",
    "composite",
})


def _fingerprint(obj: Any) -> str:
    """Return the complete deterministic SHA-256 digest."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# StrategyDescriptor — immutable strategy metadata
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StrategyDescriptor:
    """Immutable description of a single strategy variant.

    Each descriptor represents one version of one strategy.  The combination
    of ``strategy_id`` + ``strategy_version`` must be unique within a registry.
    """

    strategy_id: str
    strategy_version: str
    family: str  # e.g. "trend_following", "mean_reversion"

    # Which directions this strategy can trade
    supported_directions: tuple[int, ...]  # (1,), (-1,), or (1, -1)

    # Which H4 tradable_regime values this strategy supports
    supported_regimes: tuple[str, ...]  # e.g. ("trend_following",)

    # Which MarketState timeframes this strategy requires to be non-unknown
    required_timeframes: tuple[str, ...]  # e.g. ("1d", "4h")

    # Minimum MarketState.confidence to route
    minimum_confidence: float

    # Which conflict fields this strategy can tolerate (non-fatal)
    allowed_conflict_fields: tuple[str, ...] = ()

    # Symbol scope: empty = all symbols; otherwise whitelist
    symbol_scope: tuple[str, ...] = ()

    # Routing priority (lower = higher priority)
    priority: int = 100

    # Risk sleeve classification
    sleeve_type: str = "trend"

    # Reference to the signal provider (NOT a dynamic import target)
    signal_provider_id: str = ""

    # Lifecycle status
    research_status: str = "prototype"

    # Optional description
    description: str = ""

    # ---- Validation ----
    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if not self.strategy_version:
            raise ValueError("strategy_version must not be empty")
        if self.family not in VALID_FAMILIES:
            raise ValueError(f"Invalid family: {self.family!r}. Valid: {sorted(VALID_FAMILIES)}")
        if not self.supported_directions:
            raise ValueError("supported_directions must not be empty")
        for d in self.supported_directions:
            if d not in VALID_DIRECTIONS:
                raise ValueError(f"Invalid direction: {d}. Must be 1 or -1")
        if not self.supported_regimes:
            raise ValueError("supported_regimes must not be empty")
        invalid_regimes = set(self.supported_regimes) - {
            "trend_following", "mean_reversion", "no_trade"
        }
        if invalid_regimes:
            raise ValueError(f"Invalid supported_regimes: {sorted(invalid_regimes)}")
        if len(set(self.supported_directions)) != len(self.supported_directions):
            raise ValueError("supported_directions must not contain duplicates")
        if len(set(self.supported_regimes)) != len(self.supported_regimes):
            raise ValueError("supported_regimes must not contain duplicates")
        if not self.required_timeframes:
            raise ValueError("required_timeframes must not be empty")
        for tf in self.required_timeframes:
            if tf not in ("1w", "1d", "4h", "15m"):
                raise ValueError(f"Invalid timeframe: {tf!r}")
        if len(set(self.required_timeframes)) != len(self.required_timeframes):
            raise ValueError("required_timeframes must not contain duplicates")
        if self.research_status in ("formation_eligible", "frozen") and "4h" not in self.required_timeframes:
            raise ValueError("routable strategies must require 4h regime state")
        if not (0.0 <= self.minimum_confidence <= 1.0):
            raise ValueError(f"minimum_confidence must be in [0, 1], got {self.minimum_confidence}")
        if self.sleeve_type not in VALID_SLEEVE_TYPES:
            raise ValueError(f"Invalid sleeve_type: {self.sleeve_type!r}. Valid: {sorted(VALID_SLEEVE_TYPES)}")
        if self.research_status not in VALID_RESEARCH_STATUSES:
            raise ValueError(f"Invalid research_status: {self.research_status!r}. Valid: {sorted(VALID_RESEARCH_STATUSES)}")
        if self.priority < 0:
            raise ValueError(f"priority must be >= 0, got {self.priority}")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise ValueError("priority must be an integer")

    # ---- Serialization ----
    def to_dict(self) -> dict:
        d = asdict(self)
        d["supported_directions"] = list(self.supported_directions)
        d["supported_regimes"] = list(self.supported_regimes)
        d["required_timeframes"] = list(self.required_timeframes)
        d["allowed_conflict_fields"] = list(self.allowed_conflict_fields)
        d["symbol_scope"] = list(self.symbol_scope)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> StrategyDescriptor:
        return cls(
            strategy_id=data["strategy_id"],
            strategy_version=data["strategy_version"],
            family=data["family"],
            supported_directions=tuple(data["supported_directions"]),
            supported_regimes=tuple(data["supported_regimes"]),
            required_timeframes=tuple(data["required_timeframes"]),
            minimum_confidence=data["minimum_confidence"],
            allowed_conflict_fields=tuple(data.get("allowed_conflict_fields", [])),
            symbol_scope=tuple(data.get("symbol_scope", [])),
            priority=data.get("priority", 100),
            sleeve_type=data.get("sleeve_type", "trend"),
            signal_provider_id=data.get("signal_provider_id", ""),
            research_status=data.get("research_status", "prototype"),
            description=data.get("description", ""),
        )

    def fingerprint(self) -> str:
        """Deterministic fingerprint of this descriptor."""
        return _fingerprint(self.to_dict())

    @property
    def is_routable(self) -> bool:
        """Whether this strategy can be a routing candidate."""
        return self.research_status in ("formation_eligible", "frozen")


# ---------------------------------------------------------------------------
# StrategyRegistry — immutable collection of descriptors
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StrategyRegistry:
    """Immutable, validated collection of strategy descriptors.

    Enforces uniqueness of (strategy_id, strategy_version) and provides
    deterministic fingerprinting.
    """

    descriptors: tuple[StrategyDescriptor, ...]
    version: str = "v1.0.0"

    def __post_init__(self) -> None:
        # Enforce uniqueness
        seen: set[tuple[str, str]] = set()
        for d in self.descriptors:
            key = (d.strategy_id, d.strategy_version)
            if key in seen:
                raise ValueError(
                    f"Duplicate strategy_id + strategy_version: {d.strategy_id}@{d.strategy_version}"
                )
            seen.add(key)

    @property
    def fingerprint(self) -> str:
        """Deterministic fingerprint of the entire registry."""
        payload = {
            "version": self.version,
            "descriptors": [d.to_dict() for d in self.descriptors],
        }
        return _fingerprint(payload)

    def get_routable(self) -> tuple[StrategyDescriptor, ...]:
        """Return only descriptors eligible for routing."""
        return tuple(d for d in self.descriptors if d.is_routable)

    def get_by_id(self, strategy_id: str) -> tuple[StrategyDescriptor, ...]:
        """Return all versions of a strategy by ID."""
        return tuple(d for d in self.descriptors if d.strategy_id == strategy_id)

    def get_by_family(self, family: str) -> tuple[StrategyDescriptor, ...]:
        """Return all descriptors in a family."""
        return tuple(d for d in self.descriptors if d.family == family)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "descriptors": [d.to_dict() for d in self.descriptors],
        }

    @classmethod
    def from_dict(cls, data: dict) -> StrategyRegistry:
        return cls(
            descriptors=tuple(StrategyDescriptor.from_dict(d) for d in data["descriptors"]),
            version=data.get("version", "v1.0.0"),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, text: str) -> StrategyRegistry:
        return cls.from_dict(json.loads(text))
