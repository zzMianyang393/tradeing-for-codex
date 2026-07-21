"""Tests for the Routed Signal Replay v1."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from market import FeatureBar
from market_state_schema import (
    DailyState,
    H4State,
    M15State,
    MarketRegimeState,
    MarketState,
    StateConflict,
    WeeklyState,
    get_market_state_config_fingerprint,
    get_market_state_schema_version,
)
from strategy import Signal
from strategy_registry_v1 import StrategyDescriptor, StrategyRegistry
from strategy_router_v1 import RouteDecisionType
from routed_signal_replay_v1 import (
    AuditLogEntry,
    MarketStateSnapshotStore,
    ProviderRegistry,
    ReplayAudit,
    RoutedSignalProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_DT = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
_BAR_STEP_MS = 900_000  # 15m


def _make_state(
    *,
    weekly_dir: str = "uptrend",
    daily_dir: str = "uptrend",
    h4_regime: str = "trend_following",
    h4_dir: str = "uptrend",
    m15_entry: str = "consolidation",
    m15_momentum: str = "weak_bullish",
    confidence: float = 0.8,
    conflicts: list[StateConflict] | None = None,
    available_at: datetime | None = None,
) -> MarketState:
    dt = available_at or _BASE_DT
    return MarketState(
        weekly=WeeklyState(timeframe="1w", direction=weekly_dir, trend_strength=1.5,
                           volatility_state="normal", risk_cycle="normal"),
        daily=DailyState(timeframe="1d", direction=daily_dir, trend_stage="mature",
                         volatility_state="normal", structure="pullback"),
        h4=H4State(timeframe="4h", direction=h4_dir, tradable_regime=h4_regime,
                    trend_stage="mature", breakout_or_pullback="none",
                    volatility_state="normal"),
        m15=M15State(timeframe="15m", entry_context=m15_entry, momentum=m15_momentum,
                      local_structure="range_bound", liquidity_state="normal"),
        market_regime=MarketRegimeState(btc_state="uptrend", eth_state="uptrend",
                                         market_breadth=0.7, alt_relative_strength="broad",
                                         cross_section_dispersion=0.1),
        available_at=dt,
        source_bar_close_time=dt,
        confidence=confidence,
        state_started_at=dt,
        version="v1.1.0",
        conflicts=conflicts or [],
        is_consistent=not bool(conflicts),
    )


def _make_bars(n: int, start_ts: int = 1_700_000_000_000) -> list[FeatureBar]:
    bars = []
    for i in range(n):
        ts = start_ts + i * _BAR_STEP_MS
        bars.append(FeatureBar(
            ts=ts,
            time=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            open=100.0 + i * 0.1,
            high=101.0 + i * 0.1,
            low=99.0 + i * 0.1,
            close=100.0 + i * 0.1,
            volume_quote=10000.0,
            atr=2.0,
            atr_pct=0.02,
        ))
    return bars


def _trend_long_desc(signal_provider_id: str = "trend_long_sp") -> StrategyDescriptor:
    return StrategyDescriptor(
        strategy_id="trend_long_v1",
        strategy_version="1.0.0",
        family="trend_following",
        supported_directions=(1,),
        supported_regimes=("trend_following",),
        required_timeframes=("1d", "4h"),
        minimum_confidence=0.5,
        priority=10,
        sleeve_type="trend",
        signal_provider_id=signal_provider_id,
        research_status="formation_eligible",
    )


def _range_revert_desc(signal_provider_id: str = "range_revert_sp") -> StrategyDescriptor:
    return StrategyDescriptor(
        strategy_id="range_revert_v1",
        strategy_version="1.0.0",
        family="mean_reversion",
        supported_directions=(1, -1),
        supported_regimes=("mean_reversion",),
        required_timeframes=("4h",),
        minimum_confidence=0.3,
        priority=20,
        sleeve_type="mean_reversion",
        signal_provider_id=signal_provider_id,
        research_status="frozen",
    )


def _noop_provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    """Test provider that always returns None."""
    return None


def _always_long_provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    """Test provider that always returns a long signal."""
    return Signal(symbol=symbol, direction=1, score=3.0, regime="test", reason="test_long")


def _always_short_provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
    """Test provider that always returns a short signal."""
    return Signal(symbol=symbol, direction=-1, score=3.0, regime="test", reason="test_short")


# ---------------------------------------------------------------------------
# MarketStateSnapshotStore tests
# ---------------------------------------------------------------------------

class SnapshotStoreTests(unittest.TestCase):
    def test_put_and_get(self):
        store = MarketStateSnapshotStore()
        state = _make_state()
        store.put("BTC-USDT-SWAP", _BASE_DT, state)
        result = store.get("BTC-USDT-SWAP", _BASE_DT)
        self.assertIsNotNone(result)
        self.assertEqual(result.available_at, state.available_at)

    def test_get_missing_returns_none(self):
        store = MarketStateSnapshotStore()
        result = store.get("BTC-USDT-SWAP", _BASE_DT)
        self.assertIsNone(result)

    def test_duplicate_key_fails(self):
        store = MarketStateSnapshotStore()
        state = _make_state()
        store.put("BTC-USDT-SWAP", _BASE_DT, state)
        with self.assertRaises(ValueError):
            store.put("BTC-USDT-SWAP", _BASE_DT, state)

    def test_different_symbols_same_time_ok(self):
        store = MarketStateSnapshotStore()
        state = _make_state()
        store.put("BTC-USDT-SWAP", _BASE_DT, state)
        store.put("ETH-USDT-SWAP", _BASE_DT, state)
        self.assertEqual(len(store), 2)

    def test_different_times_same_symbol_ok(self):
        store = MarketStateSnapshotStore()
        dt1 = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 7, 16, 12, 15, 0, tzinfo=timezone.utc)
        store.put("BTC-USDT-SWAP", dt1, _make_state(available_at=dt1))
        store.put("BTC-USDT-SWAP", dt2, _make_state(available_at=dt2))
        self.assertEqual(len(store), 2)

    def test_no_forward_fill(self):
        """Missing exact snapshot must not be forward-filled."""
        store = MarketStateSnapshotStore()
        dt1 = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 7, 16, 12, 15, 0, tzinfo=timezone.utc)
        store.put("BTC-USDT-SWAP", dt1, _make_state(available_at=dt1))
        # Query for dt2 — must return None, not dt1's state
        result = store.get("BTC-USDT-SWAP", dt2)
        self.assertIsNone(result)

    def test_naive_datetime_rejected(self):
        store = MarketStateSnapshotStore()
        naive_dt = datetime(2026, 7, 16, 12, 0, 0)  # no tz
        with self.assertRaises(ValueError):
            store.put("BTC-USDT-SWAP", naive_dt, _make_state())

    def test_get_by_ts(self):
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, _make_state())
        ts_ms = int(_BASE_DT.timestamp() * 1000)
        result = store.get_by_ts("BTC-USDT-SWAP", ts_ms)
        self.assertIsNotNone(result)

    def test_symbols(self):
        store = MarketStateSnapshotStore()
        dt1 = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        dt2 = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        store.put("BTC-USDT-SWAP", dt1, _make_state(available_at=dt1))
        store.put("ETH-USDT-SWAP", dt2, _make_state(available_at=dt2))
        self.assertEqual(store.symbols(), ["BTC-USDT-SWAP", "ETH-USDT-SWAP"])


# ---------------------------------------------------------------------------
# ProviderRegistry tests
# ---------------------------------------------------------------------------

class ProviderRegistryTests(unittest.TestCase):
    def test_register_and_get(self):
        reg = ProviderRegistry()
        reg.register("test_sp", _noop_provider)
        self.assertTrue(reg.has("test_sp"))
        self.assertIs(reg.get("test_sp"), _noop_provider)

    def test_duplicate_id_fails(self):
        reg = ProviderRegistry()
        reg.register("test_sp", _noop_provider)
        with self.assertRaises(ValueError):
            reg.register("test_sp", _noop_provider)

    def test_empty_id_fails(self):
        reg = ProviderRegistry()
        with self.assertRaises(ValueError):
            reg.register("", _noop_provider)

    def test_non_callable_fails(self):
        reg = ProviderRegistry()
        with self.assertRaises(ValueError):
            reg.register("test", "not_a_function")  # type: ignore

    def test_missing_returns_none(self):
        reg = ProviderRegistry()
        self.assertIsNone(reg.get("nonexistent"))

    def test_ids_sorted(self):
        reg = ProviderRegistry()
        reg.register("z_sp", _noop_provider)
        reg.register("a_sp", _noop_provider)
        self.assertEqual(reg.ids(), ["a_sp", "z_sp"])


# ---------------------------------------------------------------------------
# RoutedSignalProvider tests
# ---------------------------------------------------------------------------

class RoutedSignalProviderBasicTests(unittest.TestCase):
    """Tests 1-3: basic snapshot lookup and halt behavior."""

    def _build(
        self,
        desc: StrategyDescriptor,
        state: MarketState,
        bar_dt: datetime | None = None,
        provider_fn=_noop_provider,
    ) -> tuple[RoutedSignalProvider, list[FeatureBar]]:
        """Build a RoutedSignalProvider with one snapshot and one registered provider."""
        reg = StrategyRegistry(descriptors=(desc,))
        store = MarketStateSnapshotStore()
        effective_dt = bar_dt or _BASE_DT
        store.put("BTC-USDT-SWAP", effective_dt, state)

        prov_reg = ProviderRegistry()
        if desc.signal_provider_id:
            prov_reg.register(desc.signal_provider_id, provider_fn)

        sp = RoutedSignalProvider(reg, store, prov_reg)
        bars = _make_bars(500, start_ts=int(effective_dt.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        return sp, bars

    def test_current_time_cannot_read_future_snapshot(self):
        """Test 1: a future state cannot be stored under the current key."""
        # Store snapshot at bar_dt, but with available_at in the future
        # This simulates a snapshot that "comes from the future"
        future_dt = datetime(2026, 7, 16, 18, 0, 0, tzinfo=timezone.utc)
        state = _make_state(available_at=future_dt)
        with self.assertRaises(ValueError):
            self._build(_trend_long_desc(), state, bar_dt=_BASE_DT)

    def test_out_of_order_snapshot_insertion_rejected(self):
        store = MarketStateSnapshotStore()
        later = datetime(2026, 7, 16, 12, 15, tzinfo=timezone.utc)
        store.put("BTC-USDT-SWAP", later, _make_state(available_at=later))
        with self.assertRaises(ValueError):
            store.put("BTC-USDT-SWAP", _BASE_DT, _make_state(available_at=_BASE_DT))

    def test_missing_snapshot_no_trade(self):
        """Test 2: missing exact snapshot → no trade."""
        # Put snapshot at 12:00 but query at 12:15 (different bar)
        state = _make_state(available_at=_BASE_DT)
        sp, bars = self._build(_trend_long_desc(), state)

        # Find a bar that's NOT at _BASE_DT
        # bars start 260 bars before _BASE_DT, so idx=260 is at _BASE_DT
        # idx=261 is at _BASE_DT + 15m — no snapshot for that
        result = sp("BTC-USDT-SWAP", bars, 261)
        self.assertIsNone(result)
        self.assertEqual(sp.audit.missing_snapshot_count, 1)

    def test_halt_conflict_no_provider_call(self):
        """Test 3: HALT_CONFLICT does not call provider."""
        conflict = StateConflict(
            timeframe_a="1w", timeframe_b="1d", field="direction",
            value_a="uptrend", value_b="downtrend", severity="high",
            description="test conflict",
        )
        state = _make_state(conflicts=[conflict])
        desc = _trend_long_desc()
        sp, bars = self._build(desc, state)
        result = sp("BTC-USDT-SWAP", bars, 260)
        self.assertIsNone(result)
        self.assertEqual(sp.audit.provider_call_count, 0)
        self.assertEqual(sp.audit.halt_conflict_count, 1)


class RouterDecisionTests(unittest.TestCase):
    """Tests 4-5: HALT_UNKNOWN and HALT_NO_MATCH behavior."""

    def test_halt_unknown_no_provider_call(self):
        """Test 4: HALT_UNKNOWN (schema mismatch) does not call provider."""
        state = _make_state()
        desc = _trend_long_desc()
        reg = StrategyRegistry(descriptors=(desc,))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, state)

        prov_reg = ProviderRegistry()
        prov_reg.register("trend_long_sp", _noop_provider)

        sp = RoutedSignalProvider(
            reg, store, prov_reg,
            expected_schema_version="WRONG_VERSION",
        )
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        result = sp("BTC-USDT-SWAP", bars, 260)
        self.assertIsNone(result)
        self.assertEqual(sp.audit.provider_call_count, 0)
        self.assertEqual(sp.audit.halt_unknown_count, 1)

    def test_halt_no_match_no_provider_call(self):
        """Test 5: HALT_NO_MATCH does not call provider."""
        # trend_long needs trend_following regime, give it mean_reversion
        state = _make_state(h4_regime="mean_reversion")
        desc = _trend_long_desc()
        sp, bars = self._build(desc, state)
        result = sp("BTC-USDT-SWAP", bars, 260)
        self.assertIsNone(result)
        self.assertEqual(sp.audit.provider_call_count, 0)
        self.assertEqual(sp.audit.halt_no_match_count, 1)

    def _build(self, desc, state, bar_dt=None, provider_fn=_noop_provider):
        reg = StrategyRegistry(descriptors=(desc,))
        store = MarketStateSnapshotStore()
        effective_dt = bar_dt or _BASE_DT
        store.put("BTC-USDT-SWAP", effective_dt, state)
        prov_reg = ProviderRegistry()
        if desc.signal_provider_id:
            prov_reg.register(desc.signal_provider_id, provider_fn)
        sp = RoutedSignalProvider(reg, store, prov_reg)
        bars = _make_bars(500, start_ts=int(effective_dt.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        return sp, bars


class ProviderSelectionTests(unittest.TestCase):
    """Tests 6-8: provider selection priority."""

    def test_route_calls_first_priority_provider(self):
        """Test 6: ROUTE calls only the first (highest priority) provider."""
        high_pri = StrategyDescriptor(
            strategy_id="high_pri_v1", strategy_version="1.0.0",
            family="trend_following", supported_directions=(1,),
            supported_regimes=("trend_following",), required_timeframes=("4h",),
            minimum_confidence=0.5, priority=5,
            signal_provider_id="high_pri_sp", research_status="formation_eligible",
        )
        low_pri = StrategyDescriptor(
            strategy_id="low_pri_v1", strategy_version="1.0.0",
            family="breakout", supported_directions=(1,),
            supported_regimes=("trend_following",), required_timeframes=("4h",),
            minimum_confidence=0.5, priority=50,
            signal_provider_id="low_pri_sp", research_status="formation_eligible",
        )
        reg = StrategyRegistry(descriptors=(low_pri, high_pri))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, _make_state())

        high_called = []
        low_called = []

        def high_fn(sym, bars, idx):
            high_called.append(idx)
            return Signal(sym, 1, 3.0, "test", "high")

        def low_fn(sym, bars, idx):
            low_called.append(idx)
            return Signal(sym, 1, 3.0, "test", "low")

        prov_reg = ProviderRegistry()
        prov_reg.register("high_pri_sp", high_fn)
        prov_reg.register("low_pri_sp", low_fn)

        sp = RoutedSignalProvider(reg, store, prov_reg)
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        result = sp("BTC-USDT-SWAP", bars, 260)

        # Only high_pri should have been called
        self.assertIsNotNone(result)
        self.assertEqual(len(high_called), 1)
        self.assertEqual(len(low_called), 0)
        self.assertEqual(result.reason, "high")  # type: ignore

    def test_unselected_provider_call_count_zero(self):
        """Test 7: unselected provider has 0 calls."""
        high_pri = StrategyDescriptor(
            strategy_id="high_pri_v1", strategy_version="1.0.0",
            family="trend_following", supported_directions=(1,),
            supported_regimes=("trend_following",), required_timeframes=("4h",),
            minimum_confidence=0.5, priority=5,
            signal_provider_id="high_pri_sp", research_status="formation_eligible",
        )
        low_pri = StrategyDescriptor(
            strategy_id="low_pri_v1", strategy_version="1.0.0",
            family="breakout", supported_directions=(1,),
            supported_regimes=("trend_following",), required_timeframes=("4h",),
            minimum_confidence=0.5, priority=50,
            signal_provider_id="low_pri_sp", research_status="formation_eligible",
        )
        reg = StrategyRegistry(descriptors=(low_pri, high_pri))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, _make_state())

        low_called = []

        def low_fn(sym, bars, idx):
            low_called.append(1)
            return Signal(sym, 1, 3.0, "test", "low")

        prov_reg = ProviderRegistry()
        prov_reg.register("high_pri_sp", _always_long_provider)
        prov_reg.register("low_pri_sp", low_fn)

        sp = RoutedSignalProvider(reg, store, prov_reg)
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        sp("BTC-USDT-SWAP", bars, 260)

        self.assertEqual(len(low_called), 0)

    def test_provider_receives_causal_bars_only(self):
        """Test 8: provider only sees bars[:idx+1]."""
        received_lengths = []

        def capturing_fn(sym, bars, idx):
            received_lengths.append(len(bars))
            return None

        desc = _trend_long_desc("capture_sp")
        reg = StrategyRegistry(descriptors=(desc,))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, _make_state())

        prov_reg = ProviderRegistry()
        prov_reg.register("capture_sp", capturing_fn)

        sp = RoutedSignalProvider(reg, store, prov_reg)
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        sp("BTC-USDT-SWAP", bars, 260)

        # Provider should receive exactly 261 bars (0..260 inclusive)
        self.assertEqual(len(received_lengths), 1)
        self.assertEqual(received_lengths[0], 261)


class MissingProviderTests(unittest.TestCase):
    """Test 9: missing provider → no trade."""

    def test_missing_signal_provider_id(self):
        """Descriptor has no signal_provider_id → no trade."""
        desc = StrategyDescriptor(
            strategy_id="no_sp_v1", strategy_version="1.0.0",
            family="trend_following", supported_directions=(1,),
            supported_regimes=("trend_following",), required_timeframes=("4h",),
            minimum_confidence=0.5, priority=10,
            signal_provider_id="",  # empty
            research_status="formation_eligible",
        )
        reg = StrategyRegistry(descriptors=(desc,))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, _make_state())
        prov_reg = ProviderRegistry()

        sp = RoutedSignalProvider(reg, store, prov_reg)
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        result = sp("BTC-USDT-SWAP", bars, 260)
        self.assertIsNone(result)
        self.assertEqual(sp.audit.missing_provider_count, 1)

    def test_unregistered_provider_id(self):
        """Provider ID exists in descriptor but not registered → no trade."""
        desc = _trend_long_desc("nonexistent_sp")
        reg = StrategyRegistry(descriptors=(desc,))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, _make_state())
        prov_reg = ProviderRegistry()
        # Don't register "nonexistent_sp"

        sp = RoutedSignalProvider(reg, store, prov_reg)
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        result = sp("BTC-USDT-SWAP", bars, 260)
        self.assertIsNone(result)
        self.assertEqual(sp.audit.missing_provider_count, 1)


class DuplicateProviderTests(unittest.TestCase):
    """Test 10: duplicate provider_id fails at registration."""

    def test_duplicate_provider_fails(self):
        reg = ProviderRegistry()
        reg.register("test_sp", _noop_provider)
        with self.assertRaises(ValueError):
            reg.register("test_sp", _always_long_provider)


class FingerprintDriftTests(unittest.TestCase):
    """Test 11: schema/config fingerprint drift → halt."""

    def test_schema_drift_halts(self):
        state = _make_state()
        reg = StrategyRegistry(descriptors=(_trend_long_desc(),))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, state)
        prov_reg = ProviderRegistry()
        prov_reg.register("trend_long_sp", _always_long_provider)

        sp = RoutedSignalProvider(
            reg, store, prov_reg,
            expected_schema_version="v999.0.0",
        )
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        result = sp("BTC-USDT-SWAP", bars, 260)
        self.assertIsNone(result)
        self.assertEqual(sp.audit.halt_unknown_count, 1)

    def test_config_fp_drift_halts(self):
        state = _make_state()
        reg = StrategyRegistry(descriptors=(_trend_long_desc(),))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, state)
        prov_reg = ProviderRegistry()
        prov_reg.register("trend_long_sp", _always_long_provider)

        sp = RoutedSignalProvider(
            reg, store, prov_reg,
            expected_config_fingerprint="WRONG_FP",
        )
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        result = sp("BTC-USDT-SWAP", bars, 260)
        self.assertIsNone(result)
        self.assertEqual(sp.audit.halt_unknown_count, 1)


class DeterminismTests(unittest.TestCase):
    """Test 12: same input → identical output."""

    def test_replay_deterministic(self):
        state = _make_state()
        reg = StrategyRegistry(descriptors=(_trend_long_desc(),))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, state)
        prov_reg = ProviderRegistry()
        prov_reg.register("trend_long_sp", _always_long_provider)

        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)

        # Run 1
        sp1 = RoutedSignalProvider(reg, store, prov_reg)
        sig1 = sp1("BTC-USDT-SWAP", bars, 260)

        # Run 2 — fresh audit, same inputs
        store2 = MarketStateSnapshotStore()
        store2.put("BTC-USDT-SWAP", _BASE_DT, state)
        prov_reg2 = ProviderRegistry()
        prov_reg2.register("trend_long_sp", _always_long_provider)
        sp2 = RoutedSignalProvider(reg, store2, prov_reg2)
        sig2 = sp2("BTC-USDT-SWAP", bars, 260)

        self.assertEqual(sig1 is not None, sig2 is not None)
        if sig1 and sig2:
            self.assertEqual(sig1.direction, sig2.direction)
            self.assertEqual(sig1.score, sig2.score)
            self.assertEqual(sig1.reason, sig2.reason)

        # Audit fingerprints should match
        self.assertEqual(sp1.audit.registry_fingerprint, sp2.audit.registry_fingerprint)


class AuditLogTests(unittest.TestCase):
    """Test 13: audit log does not contain account data."""

    def test_no_account_data_in_log(self):
        state = _make_state()
        reg = StrategyRegistry(descriptors=(_trend_long_desc(),))
        store = MarketStateSnapshotStore()
        store.put("BTC-USDT-SWAP", _BASE_DT, state)
        prov_reg = ProviderRegistry()
        prov_reg.register("trend_long_sp", _always_long_provider)

        sp = RoutedSignalProvider(reg, store, prov_reg)
        bars = _make_bars(500, start_ts=int(_BASE_DT.timestamp() * 1000) - 260 * _BAR_STEP_MS)
        sp("BTC-USDT-SWAP", bars, 260)

        audit_dict = sp.audit.to_dict()
        for forbidden in ("equity", "pnl", "return_pct", "win_rate", "backtest_phase"):
            self.assertNotIn(forbidden, audit_dict)

        for entry in sp.audit.entries:
            entry_dict = entry.to_dict()
            for forbidden in ("equity", "pnl", "return_pct", "win_rate", "backtest_phase"):
                self.assertNotIn(forbidden, entry_dict)


class IntegrationTests(unittest.TestCase):
    """Tests 14-16: integration with Backtester.run_slice."""

    def test_synthetic_provider_produces_trade(self):
        """Test 14: use a synthetic provider with Backtester.run_slice to produce a real trade."""
        from backtester import Backtester
        from research_protocol import FrozenParams, CostModel

        # Create a provider that signals long when price > 120
        def price_threshold_provider(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
            if idx < 1:
                return None
            if bars[idx].close > 120.0:
                return Signal(symbol=symbol, direction=1, score=4.0, regime="test", reason="threshold_long")
            return None

        state = _make_state()
        reg = StrategyRegistry(descriptors=(
            StrategyDescriptor(
                strategy_id="threshold_v1", strategy_version="1.0.0",
                family="trend_following", supported_directions=(1,),
                supported_regimes=("trend_following",), required_timeframes=("4h",),
                minimum_confidence=0.5, priority=10,
                signal_provider_id="threshold_sp",
                research_status="formation_eligible",
            ),
        ))
        store = MarketStateSnapshotStore()
        prov_reg = ProviderRegistry()
        prov_reg.register("threshold_sp", price_threshold_provider)

        # Create800 bars: warmup (500) + trading (300)
        # Price rises from 100 to 200 across all bars
        # select_symbols needs idx >= 260 in merged market
        base_ts = 1_700_000_000_000
        n_total = 800
        n_warmup = 500  # enough for select_symbols (needs 260)
        bars: list[FeatureBar] = []
        for i in range(n_total):
            ts = base_ts + i * _BAR_STEP_MS
            price = 100.0 + (i / n_total) * 100.0  # 100 → 200
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            bars.append(FeatureBar(
                ts=ts, time=dt.strftime("%Y-%m-%d %H:%M:%S"),
                open=price - 0.2, high=price + 0.3, low=price - 0.3, close=price,
                volume_quote=500_000.0, atr=0.6, atr_pct=0.005,
                ema20=price * 0.99, ema50=price * 0.98, ema200=price * 0.97,
                rsi=55.0, bb_mid=price, bb_upper=price + 2.0, bb_lower=price - 2.0,
                vol_sma=500_000.0, donchian_high=price + 3.0, donchian_low=price - 3.0,
                trend_strength=1.0,
            ))
            store.put("BTC-USDT-SWAP", dt, _make_state(available_at=dt))

        start_ts = bars[n_warmup].ts  # first trading bar
        end_ts = bars[n_total - 1].ts
        trading_market = {"BTC-USDT-SWAP": [b for b in bars if start_ts <= b.ts <= end_ts]}
        warmup_market = {"BTC-USDT-SWAP": [b for b in bars if b.ts < start_ts]}

        config = FrozenParams().to_backtest_config(CostModel())
        sp = RoutedSignalProvider(reg, store, prov_reg)
        tester = Backtester(config)

        result = tester.run_slice(
            trading_market, warmup_market, start_ts, end_ts,
            signal_provider=sp,
        )

        # At least one trade should have been produced
        self.assertTrue(result.get("available", False))
        self.assertGreater(result.get("trades", 0), 0,
                           "Expected at least one trade from synthetic provider")

    def test_trade_time_within_slice(self):
        """Test 15: all trade entry times must be within the current slice."""
        from backtester import Backtester
        from research_protocol import FrozenParams, CostModel

        def always_signal(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None:
            if idx < 260:
                return None
            return Signal(symbol=symbol, direction=1, score=4.0, regime="test", reason="always_long")

        state = _make_state()
        reg = StrategyRegistry(descriptors=(
            StrategyDescriptor(
                strategy_id="always_v1", strategy_version="1.0.0",
                family="trend_following", supported_directions=(1,),
                supported_regimes=("trend_following",), required_timeframes=("4h",),
                minimum_confidence=0.5, priority=10,
                signal_provider_id="always_sp",
                research_status="formation_eligible",
            ),
        ))
        store = MarketStateSnapshotStore()
        prov_reg = ProviderRegistry()
        prov_reg.register("always_sp", always_signal)

        base_ts = 1_700_000_000_000
        n_total = 800
        n_warmup = 500
        bars: list[FeatureBar] = []
        for i in range(n_total):
            ts = base_ts + i * _BAR_STEP_MS
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            bars.append(FeatureBar(
                ts=ts, time=dt.strftime("%Y-%m-%d %H:%M:%S"),
                open=100.0, high=101.0, low=99.0, close=100.0 + i * 0.01,
                volume_quote=500_000.0, atr=2.0, atr_pct=0.02,
                ema20=100.0, ema50=100.0, ema200=100.0,
                rsi=50.0, bb_mid=100.0, bb_upper=105.0, bb_lower=95.0,
                vol_sma=500_000.0, donchian_high=110.0, donchian_low=90.0,
                trend_strength=0.5,
            ))
            store.put("BTC-USDT-SWAP", dt, _make_state(available_at=dt))

        config = FrozenParams().to_backtest_config(CostModel())
        sp = RoutedSignalProvider(reg, store, prov_reg)
        tester = Backtester(config)

        start_ts = bars[n_warmup].ts
        end_ts = bars[n_total - 1].ts
        trading = {"BTC-USDT-SWAP": [b for b in bars if start_ts <= b.ts <= end_ts]}
        warmup = {"BTC-USDT-SWAP": [b for b in bars if b.ts < start_ts]}

        result = tester.run_slice(trading, warmup, start_ts, end_ts, signal_provider=sp)

        if result.get("available") and result.get("trades_detail"):
            for trade in result["trades_detail"]:
                entry_ts = int(datetime.strptime(
                    trade["entry_time"], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc).timestamp() * 1000)
                self.assertGreaterEqual(entry_ts, start_ts,
                                        f"Trade entry {trade['entry_time']} before slice start")
                self.assertLessEqual(entry_ts, end_ts,
                                     f"Trade entry {trade['entry_time']} after slice end")

    def test_does_not_call_runner_or_executor(self):
        """Test 16: module imports do not pull in runner.py or executor.py."""
        import routed_signal_replay_v1 as mod
        source = open(mod.__file__, "r", encoding="utf-8").read() if mod.__file__ else ""
        self.assertNotIn("from runner import", source)
        self.assertNotIn("from executor import", source)
        self.assertNotIn("import runner", source)
        self.assertNotIn("import executor", source)


class FormalStatusTests(unittest.TestCase):
    """Verify formal_status is always infrastructure_only."""

    def test_formal_status_default(self):
        audit = ReplayAudit()
        self.assertEqual(audit.formal_status, "infrastructure_only")

    def test_formal_status_in_dict(self):
        audit = ReplayAudit()
        d = audit.to_dict()
        self.assertEqual(d["formal_status"], "infrastructure_only")


if __name__ == "__main__":
    unittest.main()
