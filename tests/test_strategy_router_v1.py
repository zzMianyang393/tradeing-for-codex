"""Tests for the Strategy Router v1."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from market_state_schema import (
    DailyState,
    H4State,
    M15State,
    MarketRegimeState,
    MarketState,
    MarketStateConfig,
    StateConflict,
    WeeklyState,
    get_market_state_config_fingerprint,
    get_market_state_schema_version,
)
from strategy_registry_v1 import StrategyDescriptor, StrategyRegistry
from strategy_router_v1 import (
    ReasonCode,
    RouteDecisionType,
    route,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic MarketState for testing
# ---------------------------------------------------------------------------

_BASE_DT = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)


def _make_state(
    weekly_dir: str = "uptrend",
    daily_dir: str = "uptrend",
    h4_regime: str = "trend_following",
    h4_dir: str = "uptrend",
    m15_entry: str = "consolidation",
    m15_momentum: str = "weak_bullish",
    confidence: float = 0.8,
    conflicts: list[StateConflict] | None = None,
    insufficient: list[str] | None = None,
    daily_stage: str = "mature",
    weekly_vol: str = "normal",
    daily_vol: str = "normal",
    h4_vol: str = "normal",
) -> MarketState:
    return MarketState(
        weekly=WeeklyState(
            timeframe="1w",
            direction=weekly_dir,
            trend_strength=1.5,
            volatility_state=weekly_vol,
            risk_cycle="normal",
        ),
        daily=DailyState(
            timeframe="1d",
            direction=daily_dir,
            trend_stage=daily_stage,
            volatility_state=daily_vol,
            structure="pullback",
        ),
        h4=H4State(
            timeframe="4h",
            direction=h4_dir,
            tradable_regime=h4_regime,
            trend_stage="mature",
            breakout_or_pullback="none",
            volatility_state=h4_vol,
        ),
        m15=M15State(
            timeframe="15m",
            entry_context=m15_entry,
            momentum=m15_momentum,
            local_structure="range_bound",
            liquidity_state="normal",
        ),
        market_regime=MarketRegimeState(
            btc_state="uptrend",
            eth_state="uptrend",
            market_breadth=0.7,
            alt_relative_strength="broad",
            cross_section_dispersion=0.1,
        ),
        available_at=_BASE_DT,
        source_bar_close_time=_BASE_DT,
        confidence=confidence,
        state_started_at=_BASE_DT,
        version="v1.1.0",
        insufficient_data_reasons=insufficient or [],
        conflicts=conflicts or [],
        is_consistent=not bool(conflicts) and not bool(insufficient),
    )


# ---------------------------------------------------------------------------
# Helpers — synthetic StrategyDescriptors
# ---------------------------------------------------------------------------

def _trend_long() -> StrategyDescriptor:
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
        research_status="formation_eligible",
    )


def _range_revert() -> StrategyDescriptor:
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
        research_status="frozen",
    )


def _downtrend_short() -> StrategyDescriptor:
    return StrategyDescriptor(
        strategy_id="downtrend_short_v1",
        strategy_version="1.0.0",
        family="trend_following",
        supported_directions=(-1,),
        supported_regimes=("trend_following",),
        required_timeframes=("1w", "1d", "4h"),
        minimum_confidence=0.6,
        priority=15,
        sleeve_type="trend",
        research_status="formation_eligible",
    )


def _breakout_both() -> StrategyDescriptor:
    return StrategyDescriptor(
        strategy_id="breakout_v1",
        strategy_version="1.0.0",
        family="breakout",
        supported_directions=(1, -1),
        supported_regimes=("trend_following", "mean_reversion"),
        required_timeframes=("4h",),
        minimum_confidence=0.4,
        priority=30,
        sleeve_type="breakout",
        research_status="formation_eligible",
    )


def _prototype() -> StrategyDescriptor:
    return StrategyDescriptor(
        strategy_id="proto_v1",
        strategy_version="0.1.0",
        family="momentum",
        supported_directions=(1,),
        supported_regimes=("trend_following",),
        required_timeframes=("4h",),
        minimum_confidence=0.0,
        research_status="prototype",
    )


def _rejected() -> StrategyDescriptor:
    return StrategyDescriptor(
        strategy_id="rejected_v1",
        strategy_version="1.0.0",
        family="breakout",
        supported_directions=(1, -1),
        supported_regimes=("trend_following", "mean_reversion"),
        required_timeframes=("4h",),
        minimum_confidence=0.0,
        research_status="rejected",
    )


def _disabled() -> StrategyDescriptor:
    return StrategyDescriptor(
        strategy_id="disabled_v1",
        strategy_version="1.0.0",
        family="carry",
        supported_directions=(1,),
        supported_regimes=("trend_following",),
        required_timeframes=("1d",),
        minimum_confidence=0.0,
        research_status="disabled",
    )


def _full_registry() -> StrategyRegistry:
    return StrategyRegistry(descriptors=(
        _trend_long(),
        _range_revert(),
        _downtrend_short(),
        _breakout_both(),
        _prototype(),
        _rejected(),
        _disabled(),
    ))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class RouterBasicTests(unittest.TestCase):
    def test_uptrend_routes_trend_long(self):
        state = _make_state(weekly_dir="uptrend", daily_dir="uptrend", h4_regime="trend_following", h4_dir="uptrend")
        reg = StrategyRegistry(descriptors=(_trend_long(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)
        self.assertIn("trend_long_v1@1.0.0", decision.selected_strategy_ids)

    def test_uptrend_does_not_route_downtrend_short(self):
        state = _make_state(weekly_dir="uptrend", daily_dir="uptrend", h4_regime="trend_following", h4_dir="uptrend")
        reg = StrategyRegistry(descriptors=(_downtrend_short(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        # downtrend_short requires direction=-1 but market is uptrend
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)

    def test_downtrend_routes_downtrend_short(self):
        state = _make_state(weekly_dir="downtrend", daily_dir="downtrend", h4_regime="trend_following", h4_dir="downtrend")
        reg = StrategyRegistry(descriptors=(_downtrend_short(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)
        self.assertIn("downtrend_short_v1@1.0.0", decision.selected_strategy_ids)

    def test_range_routes_range_revert(self):
        state = _make_state(weekly_dir="range", daily_dir="range", h4_regime="mean_reversion", h4_dir="range")
        reg = StrategyRegistry(descriptors=(_range_revert(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)
        self.assertIn("range_revert_v1@1.0.0", decision.selected_strategy_ids)

    def test_range_does_not_route_trend_long(self):
        state = _make_state(weekly_dir="range", daily_dir="range", h4_regime="mean_reversion", h4_dir="range")
        reg = StrategyRegistry(descriptors=(_trend_long(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)


class RouterRegimeTests(unittest.TestCase):
    def test_trend_strategy_not_routed_in_mean_reversion(self):
        state = _make_state(h4_regime="mean_reversion")
        reg = StrategyRegistry(descriptors=(_trend_long(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)
        rejected_ids = {r.strategy_id for r in decision.rejected_candidates}
        self.assertIn("trend_long_v1", rejected_ids)

    def test_range_strategy_not_routed_in_trend_following(self):
        state = _make_state(h4_regime="trend_following")
        reg = StrategyRegistry(descriptors=(_range_revert(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)

    def test_no_trade_halts(self):
        state = _make_state(h4_regime="no_trade")
        reg = StrategyRegistry(descriptors=(_trend_long(), _range_revert()))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)


class RouterDirectionTests(unittest.TestCase):
    def test_15m_cannot_override_daily_direction(self):
        """15m shows bearish momentum but daily/weekly are uptrend → trend_long still routes."""
        state = _make_state(
            weekly_dir="uptrend",
            daily_dir="uptrend",
            h4_regime="trend_following",
            h4_dir="uptrend",
            m15_momentum="strong_bearish",  # 15m bearish
        )
        reg = StrategyRegistry(descriptors=(_trend_long(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        # Should still route because 15m cannot override 1d direction
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)

    def test_weekly_direction_gates_strategy(self):
        """Weekly downtrend prevents long-only strategy even if daily is uptrend."""
        state = _make_state(
            weekly_dir="downtrend",
            daily_dir="uptrend",  # conflicting but weekly takes precedence
            h4_regime="trend_following",
            h4_dir="uptrend",
        )
        reg = StrategyRegistry(descriptors=(_trend_long(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_CONFLICT)


class RouterConflictTests(unittest.TestCase):
    def test_severe_direction_conflict_halts(self):
        conflict = StateConflict(
            timeframe_a="1w",
            timeframe_b="1d",
            field="direction",
            value_a="uptrend",
            value_b="downtrend",
            severity="high",
            description="Weekly uptrend vs daily downtrend",
        )
        state = _make_state(conflicts=[conflict])
        reg = StrategyRegistry(descriptors=(_trend_long(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_CONFLICT)
        self.assertIn(ReasonCode.SEVERE_DIRECTION_CONFLICT, decision.reason_codes)

    def test_medium_conflict_allowed_by_strategy(self):
        """Strategy that declares allowed_conflict_fields can tolerate medium conflicts."""
        conflict = StateConflict(
            timeframe_a="1d",
            timeframe_b="4h",
            field="direction_regime",
            value_a="uptrend",
            value_b="mean_reversion",
            severity="medium",
            description="Daily uptrend but 4h mean_reversion",
        )
        state = _make_state(conflicts=[conflict], h4_regime="mean_reversion", h4_dir="range")
        # Create a strategy that tolerates direction_regime conflicts
        tolerant = StrategyDescriptor(
            strategy_id="tolerant_v1",
            strategy_version="1.0.0",
            family="mean_reversion",
            supported_directions=(1, -1),
            supported_regimes=("mean_reversion",),
            required_timeframes=("4h",),
            minimum_confidence=0.3,
            allowed_conflict_fields=("direction_regime",),
            research_status="formation_eligible",
        )
        reg = StrategyRegistry(descriptors=(tolerant,))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)

    def test_medium_conflict_rejected_by_default(self):
        """By default, strategies do not tolerate medium conflicts."""
        conflict = StateConflict(
            timeframe_a="1d",
            timeframe_b="4h",
            field="direction_regime",
            value_a="uptrend",
            value_b="mean_reversion",
            severity="medium",
            description="Daily uptrend but 4h mean_reversion",
        )
        state = _make_state(conflicts=[conflict], h4_regime="mean_reversion", h4_dir="range")
        # range_revert does NOT declare allowed_conflict_fields
        reg = StrategyRegistry(descriptors=(_range_revert(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)


class RouterUnknownTests(unittest.TestCase):
    def test_unknown_required_timeframe_rejects(self):
        """If a required timeframe has unknown direction/regime, reject that strategy."""
        state = _make_state(daily_dir="unknown")
        reg = StrategyRegistry(descriptors=(_trend_long(),))  # requires 1d
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)
        if decision.rejected_candidates:
            self.assertIn(
                ReasonCode.REQUIRED_TIMEFRAME_UNKNOWN,
                decision.rejected_candidates[0].reason_codes,
            )

    def test_unknown_non_required_timeframe_ok(self):
        """Unknown in a non-required timeframe is fine."""
        state = _make_state(weekly_dir="unknown")  # trend_long doesn't require 1w
        reg = StrategyRegistry(descriptors=(_trend_long(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)


class RouterLifecycleTests(unittest.TestCase):
    def test_prototype_not_routed(self):
        state = _make_state()
        reg = StrategyRegistry(descriptors=(_prototype(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)

    def test_rejected_not_routed(self):
        state = _make_state()
        reg = StrategyRegistry(descriptors=(_rejected(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)

    def test_disabled_not_routed(self):
        state = _make_state()
        reg = StrategyRegistry(descriptors=(_disabled(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)

    def test_mixed_lifecycle_only_routable_ones_route(self):
        state = _make_state()
        reg = _full_registry()
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)
        # Only formation_eligible and frozen should be selected
        for sid in decision.selected_strategy_ids:
            strat_id = sid.split("@")[0]
            self.assertIn(strat_id, ("trend_long_v1", "breakout_v1"))


class RouterNoDefaultTests(unittest.TestCase):
    def test_no_matching_strategy_abstains(self):
        """When no strategy matches, must HALT_NO_MATCH, not pick a default."""
        state = _make_state(h4_regime="no_trade")
        reg = StrategyRegistry(descriptors=(_trend_long(), _range_revert()))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)
        self.assertEqual(len(decision.selected_strategy_ids), 0)
        self.assertIn(ReasonCode.NO_MATCHING_STRATEGY, decision.reason_codes)


class RouterDeterminismTests(unittest.TestCase):
    def test_same_input_same_output(self):
        state = _make_state()
        reg = _full_registry()
        d1 = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        d2 = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(d1.decision, d2.decision)
        self.assertEqual(d1.selected_strategy_ids, d2.selected_strategy_ids)
        self.assertEqual(d1.market_state_snapshot_id, d2.market_state_snapshot_id)

    def test_same_input_same_fingerprint(self):
        state = _make_state()
        reg = _full_registry()
        d1 = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        d2 = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(d1.registry_fingerprint, d2.registry_fingerprint)

    def test_registration_order_does_not_affect_selection(self):
        """Stable sort by (priority, strategy_id) means order in registry doesn't matter."""
        state = _make_state()
        reg1 = StrategyRegistry(descriptors=(_trend_long(), _breakout_both()))
        reg2 = StrategyRegistry(descriptors=(_breakout_both(), _trend_long()))
        d1 = route(state, reg1, "BTC-USDT-SWAP", _BASE_DT)
        d2 = route(state, reg2, "BTC-USDT-SWAP", _BASE_DT)
        # Both should select the same strategies in the same order
        self.assertEqual(d1.selected_strategy_ids, d2.selected_strategy_ids)


class RouterValidationTests(unittest.TestCase):
    def test_available_at_mismatch_rejects(self):
        state = _make_state()
        reg = _full_registry()
        wrong_dt = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)
        decision = route(state, reg, "BTC-USDT-SWAP", wrong_dt)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_UNKNOWN)
        self.assertIn(ReasonCode.AVAILABLE_AT_MISMATCH, decision.reason_codes)

    def test_schema_version_mismatch_rejects(self):
        state = _make_state()
        reg = _full_registry()
        decision = route(
            state, reg, "BTC-USDT-SWAP", _BASE_DT,
            expected_schema_version="WRONG_VERSION",
        )
        self.assertEqual(decision.decision, RouteDecisionType.HALT_UNKNOWN)
        self.assertIn(ReasonCode.SCHEMA_VERSION_MISMATCH, decision.reason_codes)

    def test_config_fingerprint_mismatch_rejects(self):
        state = _make_state()
        reg = _full_registry()
        decision = route(
            state, reg, "BTC-USDT-SWAP", _BASE_DT,
            expected_config_fingerprint="WRONG_FINGERPRINT",
        )
        self.assertEqual(decision.decision, RouteDecisionType.HALT_UNKNOWN)
        self.assertIn(ReasonCode.CONFIG_FINGERPRINT_MISMATCH, decision.reason_codes)

    def test_valid_schema_version_passes(self):
        state = _make_state()
        reg = _full_registry()
        decision = route(
            state, reg, "BTC-USDT-SWAP", _BASE_DT,
            expected_schema_version=get_market_state_schema_version(),
        )
        # Should not halt on schema mismatch
        self.assertNotEqual(decision.decision, RouteDecisionType.HALT_UNKNOWN)

    def test_valid_config_fingerprint_passes(self):
        state = _make_state()
        reg = _full_registry()
        decision = route(
            state, reg, "BTC-USDT-SWAP", _BASE_DT,
            expected_config_fingerprint=get_market_state_config_fingerprint(),
        )
        self.assertNotEqual(decision.decision, RouteDecisionType.HALT_UNKNOWN)


class RouterConfidenceTests(unittest.TestCase):
    def test_low_confidence_rejects(self):
        state = _make_state(confidence=0.1)
        reg = StrategyRegistry(descriptors=(_trend_long(),))  # min_confidence=0.5
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.HALT_NO_MATCH)

    def test_high_confidence_routes(self):
        state = _make_state(confidence=0.9)
        reg = StrategyRegistry(descriptors=(_trend_long(),))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)


class RouterStableSortTests(unittest.TestCase):
    def test_priority_determines_order(self):
        """Lower priority number = higher priority = selected first."""
        state = _make_state()
        high_pri = StrategyDescriptor(
            strategy_id="high_pri",
            strategy_version="1.0",
            family="trend_following",
            supported_directions=(1,),
            supported_regimes=("trend_following",),
            required_timeframes=("4h",),
            minimum_confidence=0.0,
            priority=5,
            research_status="formation_eligible",
        )
        low_pri = StrategyDescriptor(
            strategy_id="low_pri",
            strategy_version="1.0",
            family="breakout",
            supported_directions=(1,),
            supported_regimes=("trend_following",),
            required_timeframes=("4h",),
            minimum_confidence=0.0,
            priority=50,
            research_status="formation_eligible",
        )
        reg = StrategyRegistry(descriptors=(low_pri, high_pri))
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(decision.decision, RouteDecisionType.ROUTE)
        # high_pri should come first
        self.assertEqual(decision.selected_strategy_ids[0], "high_pri@1.0")
        self.assertEqual(decision.selected_strategy_ids[1], "low_pri@1.0")


class RouterDoesNotAccessAccountTests(unittest.TestCase):
    def test_no_account_or_pnl_in_decision(self):
        """Verify RouteDecision has no account, PnL, or backtest fields."""
        state = _make_state()
        reg = _full_registry()
        decision = route(state, reg, "BTC-USDT-SWAP", _BASE_DT)
        d = decision.to_dict()
        # These fields must NOT exist
        for forbidden in ("equity", "pnl", "return_pct", "win_rate", "backtest_phase"):
            self.assertNotIn(forbidden, d)


class RouterSymbolScopeTests(unittest.TestCase):
    def test_symbol_scope_restricts(self):
        scoped = StrategyDescriptor(
            strategy_id="scoped_v1",
            strategy_version="1.0",
            family="trend_following",
            supported_directions=(1,),
            supported_regimes=("trend_following",),
            required_timeframes=("4h",),
            minimum_confidence=0.0,
            symbol_scope=("ETH-USDT-SWAP",),
            research_status="formation_eligible",
        )
        reg = StrategyRegistry(descriptors=(scoped,))
        # Should route for ETH
        d1 = route(_make_state(), reg, "ETH-USDT-SWAP", _BASE_DT)
        self.assertEqual(d1.decision, RouteDecisionType.ROUTE)
        # Should NOT route for BTC
        d2 = route(_make_state(), reg, "BTC-USDT-SWAP", _BASE_DT)
        self.assertEqual(d2.decision, RouteDecisionType.HALT_NO_MATCH)


if __name__ == "__main__":
    unittest.main()
