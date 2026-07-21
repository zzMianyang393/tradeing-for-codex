"""Routed Signal Replay v1 — bridges Router, Registry, and Backtester signal interface.

This module connects:
- MarketState snapshots (from market_state_schema)
- StrategyRegistry + Router (strategy_registry_v1 / strategy_router_v1)
- Backtester's ExternalSignalProvider interface

It does NOT:
- Implement trading strategies
- Access account equity or PnL
- Execute orders
- Call runner.py or executor.py

Design constraints:
- ProviderRegistry uses explicit injection (no dynamic imports).
- MarketStateSnapshotStore is read-only and strictly causal.
- RoutedSignalProvider only calls providers for ROUTE decisions.
- Multiple matched strategies → only the first (by priority) is called.
- All decisions are logged for audit.
- formal_status is always "infrastructure_only".
"""

from __future__ import annotations

import json
import inspect
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from market import FeatureBar
from market_state_schema import (
    MarketState,
    ensure_utc,
    get_market_state_config_fingerprint,
    get_market_state_schema_version,
)
from strategy import Signal
from strategy_registry_v1 import StrategyDescriptor, StrategyRegistry
from strategy_router_v1 import (
    FROZEN_CONFIG_FINGERPRINT,
    FROZEN_SCHEMA_VERSION,
    RouteDecision,
    RouteDecisionType,
    RejectedCandidate,
    route,
)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
SignalProviderFn = Callable[..., Signal | None]


@dataclass(frozen=True)
class RoutedProviderContext:
    """Causal state made available to a selected signal provider."""

    market_state: MarketState
    market_state_snapshot_id: str
    available_at: datetime


# ---------------------------------------------------------------------------
# MarketStateSnapshotStore — causal, read-only snapshot storage
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SnapshotKey:
    """Composite key for snapshot lookup."""
    symbol: str
    available_at_ts: int  # milliseconds since epoch

    def __lt__(self, other: SnapshotKey) -> bool:
        if self.symbol != other.symbol:
            return self.symbol < other.symbol
        return self.available_at_ts < other.available_at_ts


class MarketStateSnapshotStore:
    """Read-only store for MarketState snapshots.

    Rules:
    - Snapshots are indexed by (symbol, available_at) with millisecond precision.
    - Rejects duplicate keys.
    - Rejects naive datetimes.
    - Only returns exact matches — no interpolation or forward-fill.
    - Missing snapshot → caller must abstain from trading.
    """

    def __init__(self) -> None:
        self._store: dict[SnapshotKey, MarketState] = {}
        self._insertion_order: list[SnapshotKey] = []
        self._latest_by_symbol: dict[str, int] = {}

    def put(self, symbol: str, available_at: datetime, state: MarketState) -> None:
        """Store a snapshot. Raises on duplicate key or naive datetime."""
        utc_dt = ensure_utc(available_at)
        if not symbol:
            raise ValueError("symbol must not be empty")
        if state.available_at != utc_dt:
            raise ValueError("snapshot key must equal state.available_at")
        if state.version != FROZEN_SCHEMA_VERSION:
            raise ValueError("snapshot schema version does not match router v1")
        key = SnapshotKey(symbol=symbol, available_at_ts=int(utc_dt.timestamp() * 1000))
        if key in self._store:
            raise ValueError(
                f"Duplicate snapshot key: {symbol} @ {utc_dt.isoformat()}"
            )
        latest = self._latest_by_symbol.get(symbol)
        if latest is not None and key.available_at_ts <= latest:
            raise ValueError("snapshot insertion must be strictly increasing per symbol")
        self._store[key] = state
        self._insertion_order.append(key)
        self._latest_by_symbol[symbol] = key.available_at_ts

    def get(self, symbol: str, available_at: datetime) -> MarketState | None:
        """Get exact snapshot. Returns None if not found (no forward-fill)."""
        utc_dt = ensure_utc(available_at)
        key = SnapshotKey(symbol=symbol, available_at_ts=int(utc_dt.timestamp() * 1000))
        return self._store.get(key)

    def get_by_ts(self, symbol: str, available_at_ms: int) -> MarketState | None:
        """Get exact snapshot by millisecond timestamp."""
        key = SnapshotKey(symbol=symbol, available_at_ts=available_at_ms)
        return self._store.get(key)

    def has(self, symbol: str, available_at: datetime) -> bool:
        utc_dt = ensure_utc(available_at)
        key = SnapshotKey(symbol=symbol, available_at_ts=int(utc_dt.timestamp() * 1000))
        return key in self._store

    def symbols(self) -> list[str]:
        return sorted({k.symbol for k in self._store})

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, item: tuple[str, datetime]) -> bool:
        symbol, dt = item
        return self.has(symbol, dt)


# ---------------------------------------------------------------------------
# ProviderRegistry — explicit injection of signal providers
# ---------------------------------------------------------------------------
class ProviderRegistry:
    """Maps signal_provider_id to callables via explicit injection.

    Rules:
    - No dynamic imports or string-based code execution.
    - Duplicate provider_id → raise ValueError.
    - Missing provider → return refusal record, do NOT call a default.
    """

    def __init__(self) -> None:
        self._providers: dict[str, SignalProviderFn] = {}

    def register(self, provider_id: str, fn: SignalProviderFn) -> None:
        """Register a signal provider callable. Raises on duplicate ID."""
        if not provider_id:
            raise ValueError("provider_id must not be empty")
        if provider_id in self._providers:
            raise ValueError(f"Duplicate provider_id: {provider_id!r}")
        if not callable(fn):
            raise ValueError(f"Provider for {provider_id!r} must be callable")
        self._providers[provider_id] = fn

    def get(self, provider_id: str) -> SignalProviderFn | None:
        """Get a provider by ID. Returns None if not found."""
        return self._providers.get(provider_id)

    def has(self, provider_id: str) -> bool:
        return provider_id in self._providers

    def ids(self) -> list[str]:
        return sorted(self._providers.keys())


# ---------------------------------------------------------------------------
# AuditLogEntry — one routing decision record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AuditLogEntry:
    """Immutable record of one routing decision during replay."""

    bar_ts: int
    bar_time: str
    symbol: str
    snapshot_id: str
    registry_fingerprint: str
    decision: str  # RouteDecisionType value
    selected_strategy_id: str  # first selected, or ""
    provider_id: str  # provider called, or ""
    signal_emitted: bool
    reason_codes: tuple[str, ...]
    rejected_candidates: tuple[str, ...]  # "id@version:reason1,reason2"

    def to_dict(self) -> dict:
        return {
            "bar_ts": self.bar_ts,
            "bar_time": self.bar_time,
            "symbol": self.symbol,
            "snapshot_id": self.snapshot_id,
            "registry_fingerprint": self.registry_fingerprint,
            "decision": self.decision,
            "selected_strategy_id": self.selected_strategy_id,
            "provider_id": self.provider_id,
            "signal_emitted": self.signal_emitted,
            "reason_codes": list(self.reason_codes),
            "rejected_candidates": list(self.rejected_candidates),
        }


# ---------------------------------------------------------------------------
# ReplayAudit — aggregate statistics
# ---------------------------------------------------------------------------
@dataclass
class ReplayAudit:
    """Aggregate audit results for a full replay run."""

    total_decisions: int = 0
    route_count: int = 0
    abstain_count: int = 0
    halt_conflict_count: int = 0
    halt_unknown_count: int = 0
    halt_no_match_count: int = 0
    provider_call_count: int = 0
    emitted_signal_count: int = 0
    missing_snapshot_count: int = 0
    missing_provider_count: int = 0
    future_access_violations: int = 0
    registry_fingerprint: str = ""
    market_state_schema_version: str = ""
    market_state_config_fingerprint: str = ""
    formal_status: str = "infrastructure_only"
    entries: list[AuditLogEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_decisions": self.total_decisions,
            "route_count": self.route_count,
            "abstain_count": self.abstain_count,
            "halt_conflict_count": self.halt_conflict_count,
            "halt_unknown_count": self.halt_unknown_count,
            "halt_no_match_count": self.halt_no_match_count,
            "provider_call_count": self.provider_call_count,
            "emitted_signal_count": self.emitted_signal_count,
            "missing_snapshot_count": self.missing_snapshot_count,
            "missing_provider_count": self.missing_provider_count,
            "future_access_violations": self.future_access_violations,
            "registry_fingerprint": self.registry_fingerprint,
            "market_state_schema_version": self.market_state_schema_version,
            "market_state_config_fingerprint": self.market_state_config_fingerprint,
            "formal_status": self.formal_status,
            "entries": [e.to_dict() for e in self.entries],
        }


# ---------------------------------------------------------------------------
# RoutedSignalProvider — the bridge
# ---------------------------------------------------------------------------
class RoutedSignalProvider:
    """Bridges Router + Registry + SnapshotStore into Backtester's signal interface.

    Callable signature: (symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None

    This matches Backtester's ExternalSignalProvider = Callable[[str, list[FeatureBar], int], Signal | None].

    Rules:
    - Looks up MarketState snapshot by current bar's timestamp.
    - Calls route() to get a RouteDecision.
    - Only calls providers for ROUTE decisions.
    - Multiple matched strategies → only the first (by priority) is called.
    - Provider receives only bars up to and including the current idx (causal prefix).
    - Does NOT access account equity, PnL, or backtest phase names.
    - Logs every decision for audit.
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        snapshot_store: MarketStateSnapshotStore,
        provider_registry: ProviderRegistry,
        audit: ReplayAudit | None = None,
        *,
        expected_schema_version: str = FROZEN_SCHEMA_VERSION,
        expected_config_fingerprint: str = FROZEN_CONFIG_FINGERPRINT,
    ) -> None:
        self._registry = registry
        self._snapshots = snapshot_store
        self._providers = provider_registry
        self._audit = audit if audit is not None else ReplayAudit()
        self._audit.registry_fingerprint = registry.fingerprint
        self._audit.market_state_schema_version = (
            expected_schema_version
        )
        self._audit.market_state_config_fingerprint = (
            expected_config_fingerprint
        )
        self._expected_schema = expected_schema_version
        self._expected_config_fp = expected_config_fingerprint

    @property
    def audit(self) -> ReplayAudit:
        return self._audit

    def __call__(self, symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
        """Backtester-compatible signal provider entry point.

        Parameters
        ----------
        symbol : str
            The symbol being evaluated (e.g. "BTC-USDT-SWAP").
        bars : list[FeatureBar]
            Full bar history for this symbol. Provider only sees bars[:idx+1].
        idx : int
            Current bar index. bars[idx] is the current bar.

        Returns
        -------
        Signal or None
            A signal if the router selects a provider that emits one, else None.
        """
        if idx < 0 or idx >= len(bars):
            return None

        current_bar = bars[idx]
        bar_ts = current_bar.ts
        bar_time = current_bar.time

        # Convert bar timestamp to datetime for snapshot lookup
        bar_dt = datetime.fromtimestamp(bar_ts / 1000.0, tz=timezone.utc)

        # 1. Look up exact MarketState snapshot
        snapshot = self._snapshots.get(symbol, bar_dt)
        if snapshot is None:
            self._audit.missing_snapshot_count += 1
            self._audit.total_decisions += 1
            self._audit.entries.append(AuditLogEntry(
                bar_ts=bar_ts,
                bar_time=bar_time,
                symbol=symbol,
                snapshot_id="",
                registry_fingerprint=self._registry.fingerprint,
                decision="NO_SNAPSHOT",
                selected_strategy_id="",
                provider_id="",
                signal_emitted=False,
                reason_codes=("missing_snapshot",),
                rejected_candidates=(),
            ))
            return None

        # 2. Check for future access violations
        #    (snapshot.available_at must not be after current bar time)
        if snapshot.available_at > bar_dt:
            self._audit.future_access_violations += 1
            self._audit.total_decisions += 1
            self._audit.entries.append(AuditLogEntry(
                bar_ts=bar_ts,
                bar_time=bar_time,
                symbol=symbol,
                snapshot_id="",
                registry_fingerprint=self._registry.fingerprint,
                decision="FUTURE_VIOLATION",
                selected_strategy_id="",
                provider_id="",
                signal_emitted=False,
                reason_codes=("future_access_violation",),
                rejected_candidates=(),
            ))
            return None

        # 3. Call the router
        decision = route(
            state=snapshot,
            registry=self._registry,
            symbol=symbol,
            available_at=bar_dt,
            expected_schema_version=self._expected_schema,
            expected_config_fingerprint=self._expected_config_fp,
        )

        # 4. Update audit counters by decision type
        self._audit.total_decisions += 1
        if decision.decision == RouteDecisionType.ROUTE:
            self._audit.route_count += 1
        elif decision.decision == RouteDecisionType.ABSTAIN:
            self._audit.abstain_count += 1
        elif decision.decision == RouteDecisionType.HALT_CONFLICT:
            self._audit.halt_conflict_count += 1
        elif decision.decision == RouteDecisionType.HALT_UNKNOWN:
            self._audit.halt_unknown_count += 1
        elif decision.decision == RouteDecisionType.HALT_NO_MATCH:
            self._audit.halt_no_match_count += 1

        # 5. If not ROUTE, log and return None (do not call any provider)
        if decision.decision != RouteDecisionType.ROUTE:
            self._audit.entries.append(AuditLogEntry(
                bar_ts=bar_ts,
                bar_time=bar_time,
                symbol=symbol,
                snapshot_id=decision.market_state_snapshot_id,
                registry_fingerprint=self._registry.fingerprint,
                decision=decision.decision.value,
                selected_strategy_id="",
                provider_id="",
                signal_emitted=False,
                reason_codes=decision.reason_codes,
                rejected_candidates=_format_rejected(decision.rejected_candidates),
            ))
            return None

        # 6. ROUTE — call only the first selected provider
        if not decision.selected_strategy_ids:
            # Should not happen with ROUTE decision, but guard anyway
            return None

        first_id = decision.selected_strategy_ids[0]
        strat_id, ver = first_id.rsplit("@", 1)

        # Find the descriptor to get the signal_provider_id
        descriptor = None
        for d in self._registry.descriptors:
            if d.strategy_id == strat_id and d.strategy_version == ver:
                descriptor = d
                break

        if descriptor is None or not descriptor.signal_provider_id:
            self._audit.missing_provider_count += 1
            self._audit.entries.append(AuditLogEntry(
                bar_ts=bar_ts,
                bar_time=bar_time,
                symbol=symbol,
                snapshot_id=decision.market_state_snapshot_id,
                registry_fingerprint=self._registry.fingerprint,
                decision="ROUTE",
                selected_strategy_id=first_id,
                provider_id="",
                signal_emitted=False,
                reason_codes=("missing_provider_id",),
                rejected_candidates=_format_rejected(decision.rejected_candidates),
            ))
            return None

        provider_fn = self._providers.get(descriptor.signal_provider_id)
        if provider_fn is None:
            self._audit.missing_provider_count += 1
            self._audit.entries.append(AuditLogEntry(
                bar_ts=bar_ts,
                bar_time=bar_time,
                symbol=symbol,
                snapshot_id=decision.market_state_snapshot_id,
                registry_fingerprint=self._registry.fingerprint,
                decision="ROUTE",
                selected_strategy_id=first_id,
                provider_id=descriptor.signal_provider_id,
                signal_emitted=False,
                reason_codes=("provider_not_registered",),
                rejected_candidates=_format_rejected(decision.rejected_candidates),
            ))
            return None

        # 7. Call provider with causal prefix only (bars[:idx+1])
        self._audit.provider_call_count += 1
        causal_bars = bars[: idx + 1]
        context = RoutedProviderContext(
            market_state=snapshot,
            market_state_snapshot_id=decision.market_state_snapshot_id,
            available_at=bar_dt,
        )
        signature = inspect.signature(provider_fn)
        accepts_context = any(
            p.kind == inspect.Parameter.VAR_POSITIONAL
            for p in signature.parameters.values()
        ) or len(signature.parameters) >= 4
        if accepts_context:
            signal = provider_fn(symbol, causal_bars, len(causal_bars) - 1, context)
        else:
            # Compatibility for infrastructure-only v1 test providers. New
            # market-state-aware providers must use the four-argument form.
            signal = provider_fn(symbol, causal_bars, len(causal_bars) - 1)

        signal_emitted = signal is not None
        if signal_emitted:
            self._audit.emitted_signal_count += 1

        self._audit.entries.append(AuditLogEntry(
            bar_ts=bar_ts,
            bar_time=bar_time,
            symbol=symbol,
            snapshot_id=decision.market_state_snapshot_id,
            registry_fingerprint=self._registry.fingerprint,
            decision="ROUTE",
            selected_strategy_id=first_id,
            provider_id=descriptor.signal_provider_id,
            signal_emitted=signal_emitted,
            reason_codes=decision.reason_codes,
            rejected_candidates=_format_rejected(decision.rejected_candidates),
        ))

        return signal


def _format_rejected(rejected: tuple[RejectedCandidate, ...]) -> tuple[str, ...]:
    """Format rejected candidates for audit log."""
    return tuple(
        f"{r.strategy_id}@{r.strategy_version}:{','.join(r.reason_codes)}"
        for r in rejected
    )
