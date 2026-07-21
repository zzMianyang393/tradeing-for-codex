"""Strategy Router v1 — pure-function MarketState → strategy matching.

This module takes a MarketState snapshot and a StrategyRegistry, and produces
a RouteDecision that says which strategies (if any) are appropriate for the
current market conditions.

Design constraints:
- Pure function: same inputs always produce identical outputs.
- No dynamic imports, no signal generation, no order execution.
- No access to account equity, PnL, or backtest phase names.
- 15m timeframe can only gate entry timing; it cannot override 1d/4h direction.
- Severe cross-timeframe direction conflicts → HALT_CONFLICT.
- unknown required_timeframe → reject that strategy.
- Multiple candidates → stable sort by (priority, strategy_id).
- No "default strategy" fallback.

Responsibility boundary:
- Router: matches market state to eligible strategies.
- Registry: describes strategies and their eligibility.
- Signal provider: produces actual entry signals (NOT this module).
- Risk/sleeve: manages position sizing (NOT this module).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from market_state_schema import (
    MarketState,
    MarketStateConfig,
    StateConflict,
    generate_snapshot_id,
    get_market_state_config_fingerprint,
    get_market_state_schema_version,
)
from strategy_registry_v1 import StrategyDescriptor, StrategyRegistry


# A v1 router is deliberately pinned to the contract accepted with tasks 1/2.
# A future MarketState contract requires a new router version, not a silent
# adoption at import time.
FROZEN_SCHEMA_VERSION = "v1.1.0"
FROZEN_CONFIG_FINGERPRINT = (
    "6b75a055e4366986b03b8b575ee8e450eb65dfc60ae4c920aafcf6d6ed31a174"
)


# ---------------------------------------------------------------------------
# Decision enum
# ---------------------------------------------------------------------------
class RouteDecisionType(str, Enum):
    ROUTE = "ROUTE"
    ABSTAIN = "ABSTAIN"
    HALT_CONFLICT = "HALT_CONFLICT"
    HALT_UNKNOWN = "HALT_UNKNOWN"
    HALT_NO_MATCH = "HALT_NO_MATCH"


# ---------------------------------------------------------------------------
# RouteDecision — the router's output
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RouteDecision:
    """Immutable output of the routing decision."""

    symbol: str
    available_at: datetime
    decision: RouteDecisionType
    selected_strategy_ids: tuple[str, ...] = ()
    rejected_candidates: tuple[RejectedCandidate, ...] = ()
    reason_codes: tuple[str, ...] = ()
    market_state_snapshot_id: str = ""
    registry_fingerprint: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "available_at": self.available_at.isoformat().replace("+00:00", "Z"),
            "decision": self.decision.value,
            "selected_strategy_ids": list(self.selected_strategy_ids),
            "rejected_candidates": [c.to_dict() for c in self.rejected_candidates],
            "reason_codes": list(self.reason_codes),
            "market_state_snapshot_id": self.market_state_snapshot_id,
            "registry_fingerprint": self.registry_fingerprint,
        }


@dataclass(frozen=True)
class RejectedCandidate:
    """Records why a specific strategy was rejected during routing."""

    strategy_id: str
    strategy_version: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "reason_codes": list(self.reason_codes),
        }


# ---------------------------------------------------------------------------
# Reason codes — machine-readable rejection/halt reasons
# ---------------------------------------------------------------------------
class ReasonCode:
    # Conflict / halt
    SEVERE_DIRECTION_CONFLICT = "severe_direction_conflict"
    SCHEMA_VERSION_MISMATCH = "schema_version_mismatch"
    CONFIG_FINGERPRINT_MISMATCH = "config_fingerprint_mismatch"
    AVAILABLE_AT_MISMATCH = "available_at_mismatch"
    INSUFFICIENT_DATA = "insufficient_data"

    # Strategy-level rejection
    NOT_ROUTABLE = "not_routable"
    REGIME_MISMATCH = "regime_mismatch"
    DIRECTION_MISMATCH = "direction_mismatch"
    REQUIRED_TIMEFRAME_UNKNOWN = "required_timeframe_unknown"
    CONFIDENCE_TOO_LOW = "confidence_too_low"
    SYMBOL_NOT_IN_SCOPE = "symbol_not_in_scope"
    UNALLOWED_CONFLICT = "unallowed_conflict"

    # No match
    NO_MATCHING_STRATEGY = "no_matching_strategy"


# ---------------------------------------------------------------------------
# Severe conflict fields — these cause HALT_CONFLICT
# ---------------------------------------------------------------------------
_SEVERE_CONFLICT_FIELDS = frozenset({"direction", "direction_regime"})


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def _get_timeframe_direction(state: MarketState, tf: str) -> str:
    """Extract direction from a specific timeframe state."""
    if tf == "1w":
        return state.weekly.direction
    elif tf == "1d":
        return state.daily.direction
    elif tf == "4h":
        return state.h4.direction
    elif tf == "15m":
        # M15 has no explicit direction; derive from momentum
        m = state.m15.momentum
        if m in ("strong_bullish", "weak_bullish"):
            return "uptrend"
        elif m in ("strong_bearish", "weak_bearish"):
            return "downtrend"
        return "unknown"
    return "unknown"


def _get_timeframe_regime(state: MarketState, tf: str) -> str:
    """Extract regime/relevant field from a timeframe for matching."""
    if tf == "4h":
        return state.h4.tradable_regime
    elif tf == "1d":
        return state.daily.direction
    elif tf == "1w":
        return state.weekly.direction
    return "unknown"


def _is_severe_conflict(conflicts: list[StateConflict]) -> bool:
    """Check if any conflict is severe and in a critical field."""
    for c in conflicts:
        if c.severity == "high" and c.field in _SEVERE_CONFLICT_FIELDS:
            return True
    return False


def _check_required_timeframes(
    state: MarketState,
    required: tuple[str, ...],
) -> list[str]:
    """Return list of required timeframes that are 'unknown'."""
    missing = []
    for tf in required:
        if tf == "1w" and state.weekly.direction == "unknown":
            missing.append(tf)
        elif tf == "1d" and state.daily.direction == "unknown":
            missing.append(tf)
        elif tf == "4h" and state.h4.tradable_regime == "unknown":
            missing.append(tf)
        elif tf == "15m" and state.m15.entry_context == "unknown":
            missing.append(tf)
    return missing


def _strategy_matches_regime(
    desc: StrategyDescriptor,
    state: MarketState,
) -> bool:
    """Check if the strategy's supported_regimes match the current H4 regime."""
    h4_regime = state.h4.tradable_regime
    # If H4 is unknown, we already handle in required_timeframe check
    if h4_regime == "unknown":
        return False
    return h4_regime in desc.supported_regimes


def _strategy_matches_direction(
    desc: StrategyDescriptor,
    state: MarketState,
) -> bool:
    """Check if the strategy's direction is compatible with the market.

    Uses the highest-timeframe direction available (1w > 1d > 4h).
    15m cannot override higher timeframes.
    """
    # Determine overall market direction from highest available timeframe
    direction = "unknown"
    if state.weekly.direction != "unknown":
        direction = state.weekly.direction
    elif state.daily.direction != "unknown":
        direction = state.daily.direction
    elif state.h4.direction != "unknown":
        direction = state.h4.direction

    if direction == "unknown":
        return True  # Can't reject on unknown direction

    # Map direction to required strategy direction
    if direction == "uptrend":
        required_dir = 1
    elif direction == "downtrend":
        required_dir = -1
    else:
        # range/transition: both directions are acceptable
        return True

    return required_dir in desc.supported_directions


def _check_conflicts(
    desc: StrategyDescriptor,
    state: MarketState,
) -> list[str]:
    """Check if unallowed conflicts are present."""
    issues = []
    for conflict in state.conflicts:
        if conflict.severity in ("high", "medium"):
            if conflict.field not in desc.allowed_conflict_fields:
                issues.append(conflict.field)
    return issues


# ---------------------------------------------------------------------------
# Main routing function
# ---------------------------------------------------------------------------

def route(
    state: MarketState,
    registry: StrategyRegistry,
    symbol: str,
    available_at: datetime,
    *,
    expected_schema_version: str = FROZEN_SCHEMA_VERSION,
    expected_config_fingerprint: str = FROZEN_CONFIG_FINGERPRINT,
) -> RouteDecision:
    """Route a MarketState to eligible strategies.

    This is a **pure function**: identical inputs always produce identical
    outputs.  It does not access accounts, PnL, or backtest data.

    Parameters
    ----------
    state : MarketState
        Current multi-timeframe market state snapshot.
    registry : StrategyRegistry
        Immutable registry of strategy descriptors.
    symbol : str
        The symbol to route (e.g. "BTC-USDT-SWAP").
    available_at : datetime
        The decision timestamp. Must match state.available_at.
    expected_schema_version : str
        Must equal the frozen v1 MarketState schema version.
    expected_config_fingerprint : str
        Must equal the frozen v1 MarketState configuration fingerprint.

    Returns
    -------
    RouteDecision
        Immutable routing decision with selected strategies and reasons.
    """
    # ---- Pre-flight checks ----
    reason_codes: list[str] = []

    # Check available_at consistency
    from market_state_schema import ensure_utc
    utc_available_at = ensure_utc(available_at)
    if utc_available_at != state.available_at:
        return RouteDecision(
            symbol=symbol,
            available_at=utc_available_at,
            decision=RouteDecisionType.HALT_UNKNOWN,
            reason_codes=(ReasonCode.AVAILABLE_AT_MISMATCH,),
        )

    # Contract checks are mandatory. Callers cannot opt out or substitute a
    # different contract while still claiming to use router v1.
    current_version = get_market_state_schema_version()
    if (
        expected_schema_version != FROZEN_SCHEMA_VERSION
        or current_version != FROZEN_SCHEMA_VERSION
        or state.version != FROZEN_SCHEMA_VERSION
    ):
        return RouteDecision(
            symbol=symbol,
            available_at=utc_available_at,
            decision=RouteDecisionType.HALT_UNKNOWN,
            reason_codes=(ReasonCode.SCHEMA_VERSION_MISMATCH,),
        )

    current_fp = get_market_state_config_fingerprint()
    if (
        expected_config_fingerprint != FROZEN_CONFIG_FINGERPRINT
        or current_fp != FROZEN_CONFIG_FINGERPRINT
    ):
        return RouteDecision(
            symbol=symbol,
            available_at=utc_available_at,
            decision=RouteDecisionType.HALT_UNKNOWN,
            reason_codes=(ReasonCode.CONFIG_FINGERPRINT_MISMATCH,),
        )

    # Do not trust callers to have populated the conflict list correctly.
    if (
        state.weekly.direction in ("uptrend", "downtrend")
        and state.daily.direction in ("uptrend", "downtrend")
        and state.weekly.direction != state.daily.direction
    ):
        return RouteDecision(
            symbol=symbol,
            available_at=utc_available_at,
            decision=RouteDecisionType.HALT_CONFLICT,
            reason_codes=(ReasonCode.SEVERE_DIRECTION_CONFLICT,),
        )

    # Check for severe conflicts → HALT_CONFLICT
    if _is_severe_conflict(state.conflicts):
        return RouteDecision(
            symbol=symbol,
            available_at=utc_available_at,
            decision=RouteDecisionType.HALT_CONFLICT,
            reason_codes=(ReasonCode.SEVERE_DIRECTION_CONFLICT,),
        )

    # ---- Filter and match candidates ----
    routable = registry.get_routable()
    selected: list[str] = []
    rejected: list[RejectedCandidate] = []

    for desc in routable:
        reject_reasons: list[str] = []

        # 1. Check research_status (already filtered by get_routable, but double-check)
        if not desc.is_routable:
            reject_reasons.append(ReasonCode.NOT_ROUTABLE)

        # 2. Check symbol scope
        if desc.symbol_scope and symbol not in desc.symbol_scope:
            reject_reasons.append(ReasonCode.SYMBOL_NOT_IN_SCOPE)

        # 3. Check required timeframes are not unknown
        missing_tfs = _check_required_timeframes(state, desc.required_timeframes)
        if missing_tfs:
            reject_reasons.append(ReasonCode.REQUIRED_TIMEFRAME_UNKNOWN)

        # 4. Check minimum confidence
        if state.confidence < desc.minimum_confidence:
            reject_reasons.append(ReasonCode.CONFIDENCE_TOO_LOW)

        # 5. Check regime match (4h tradable_regime)
        if not _strategy_matches_regime(desc, state):
            reject_reasons.append(ReasonCode.REGIME_MISMATCH)

        # 6. Check direction compatibility
        if not _strategy_matches_direction(desc, state):
            reject_reasons.append(ReasonCode.DIRECTION_MISMATCH)

        # 7. Check for unallowed conflicts
        conflict_fields = _check_conflicts(desc, state)
        if conflict_fields:
            reject_reasons.append(ReasonCode.UNALLOWED_CONFLICT)

        if reject_reasons:
            rejected.append(RejectedCandidate(
                strategy_id=desc.strategy_id,
                strategy_version=desc.strategy_version,
                reason_codes=tuple(reject_reasons),
            ))
        else:
            selected.append(f"{desc.strategy_id}@{desc.strategy_version}")

    # ---- Stable sort selected by (priority, strategy_id) ----
    # We need to sort by the original descriptors, not the string IDs
    if selected:
        selected_descs = []
        for sid in selected:
            strat_id, ver = sid.rsplit("@", 1)
            for d in routable:
                if d.strategy_id == strat_id and d.strategy_version == ver:
                    selected_descs.append(d)
                    break
        selected_descs.sort(key=lambda d: (d.priority, d.strategy_id))
        selected = [f"{d.strategy_id}@{d.strategy_version}" for d in selected_descs]

    # ---- Build decision ----
    snapshot_id = generate_snapshot_id(
        symbol=symbol,
        available_at=utc_available_at,
        config_fingerprint=FROZEN_CONFIG_FINGERPRINT,
        state=state,
    )

    if selected:
        decision = RouteDecisionType.ROUTE
        final_reasons: tuple[str, ...] = ()
    else:
        decision = RouteDecisionType.HALT_NO_MATCH
        final_reasons = (ReasonCode.NO_MATCHING_STRATEGY,)

    return RouteDecision(
        symbol=symbol,
        available_at=utc_available_at,
        decision=decision,
        selected_strategy_ids=tuple(selected),
        rejected_candidates=tuple(rejected),
        reason_codes=final_reasons,
        market_state_snapshot_id=snapshot_id,
        registry_fingerprint=registry.fingerprint,
    )
