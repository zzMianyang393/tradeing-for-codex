"""Tests for the Strategy Registry v1."""

from __future__ import annotations

import json
import unittest

from strategy_registry_v1 import (
    VALID_FAMILIES,
    VALID_RESEARCH_STATUSES,
    VALID_SLEEVE_TYPES,
    StrategyDescriptor,
    StrategyRegistry,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic strategy descriptors for testing
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
        description="Long-only trend following in uptrend regime",
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
        description="Mean reversion in range regime",
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
        description="Short-only trend following in downtrend",
    )


def _prototype_strategy() -> StrategyDescriptor:
    return StrategyDescriptor(
        strategy_id="prototype_v1",
        strategy_version="0.1.0",
        family="momentum",
        supported_directions=(1,),
        supported_regimes=("trend_following",),
        required_timeframes=("4h",),
        minimum_confidence=0.0,
        research_status="prototype",
    )


def _rejected_strategy() -> StrategyDescriptor:
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


def _disabled_strategy() -> StrategyDescriptor:
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class StrategyDescriptorTests(unittest.TestCase):
    def test_create_valid_descriptor(self):
        d = _trend_long()
        self.assertEqual(d.strategy_id, "trend_long_v1")
        self.assertEqual(d.family, "trend_following")
        self.assertEqual(d.supported_directions, (1,))

    def test_frozen_immutable(self):
        d = _trend_long()
        with self.assertRaises(AttributeError):
            d.priority = 999  # type: ignore

    def test_is_routable_formation_eligible(self):
        d = _trend_long()
        self.assertTrue(d.is_routable)

    def test_is_routable_frozen(self):
        d = _range_revert()
        self.assertTrue(d.is_routable)

    def test_not_routable_prototype(self):
        d = _prototype_strategy()
        self.assertFalse(d.is_routable)

    def test_not_routable_rejected(self):
        d = _rejected_strategy()
        self.assertFalse(d.is_routable)

    def test_not_routable_disabled(self):
        d = _disabled_strategy()
        self.assertFalse(d.is_routable)

    def test_fingerprint_deterministic(self):
        a = _trend_long()
        b = _trend_long()
        self.assertEqual(a.fingerprint(), b.fingerprint())
        self.assertEqual(len(a.fingerprint()), 64)

    def test_fingerprint_changes_with_priority(self):
        a = _trend_long()
        b = StrategyDescriptor(
            strategy_id="trend_long_v1",
            strategy_version="1.0.0",
            family="trend_following",
            supported_directions=(1,),
            supported_regimes=("trend_following",),
            required_timeframes=("1d", "4h"),
            minimum_confidence=0.5,
            priority=999,
        )
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_to_dict_roundtrip(self):
        d = _trend_long()
        raw = d.to_dict()
        d2 = StrategyDescriptor.from_dict(raw)
        self.assertEqual(d.strategy_id, d2.strategy_id)
        self.assertEqual(d.supported_directions, d2.supported_directions)
        self.assertEqual(d.fingerprint(), d2.fingerprint())

    def test_json_roundtrip(self):
        d = _trend_long()
        raw = d.to_dict()
        text = json.dumps(raw)
        d2 = StrategyDescriptor.from_dict(json.loads(text))
        self.assertEqual(d.fingerprint(), d2.fingerprint())


class StrategyDescriptorValidationTests(unittest.TestCase):
    def test_empty_strategy_id_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
            )

    def test_empty_version_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
            )

    def test_invalid_family_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="INVALID_FAMILY",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
            )

    def test_invalid_direction_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(0,),  # type: ignore
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
            )

    def test_empty_directions_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(),
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
            )

    def test_empty_regimes_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=(),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
            )

    def test_empty_timeframes_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=(),
                minimum_confidence=0.5,
            )

    def test_invalid_timeframe_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=("5m",),  # type: ignore
                minimum_confidence=0.5,
            )

    def test_confidence_out_of_range_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=1.5,
            )

    def test_invalid_sleeve_type_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
                sleeve_type="INVALID",
            )

    def test_invalid_research_status_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
                research_status="INVALID",
            )

    def test_negative_priority_fails(self):
        with self.assertRaises(ValueError):
            StrategyDescriptor(
                strategy_id="test",
                strategy_version="1.0.0",
                family="trend_following",
                supported_directions=(1,),
                supported_regimes=("trend_following",),
                required_timeframes=("4h",),
                minimum_confidence=0.5,
                priority=-1,
            )


class StrategyRegistryTests(unittest.TestCase):
    def test_create_registry(self):
        reg = StrategyRegistry(descriptors=(_trend_long(), _range_revert()))
        self.assertEqual(len(reg.descriptors), 2)

    def test_duplicate_id_version_fails(self):
        a = _trend_long()
        b = StrategyDescriptor(
            strategy_id="trend_long_v1",  # same ID
            strategy_version="1.0.0",     # same version
            family="trend_following",
            supported_directions=(1,),
            supported_regimes=("trend_following",),
            required_timeframes=("4h",),
            minimum_confidence=0.5,
        )
        with self.assertRaises(ValueError):
            StrategyRegistry(descriptors=(a, b))

    def test_same_id_different_version_ok(self):
        a = _trend_long()
        b = StrategyDescriptor(
            strategy_id="trend_long_v1",
            strategy_version="2.0.0",  # different version
            family="trend_following",
            supported_directions=(1,),
            supported_regimes=("trend_following",),
            required_timeframes=("4h",),
            minimum_confidence=0.5,
        )
        reg = StrategyRegistry(descriptors=(a, b))
        self.assertEqual(len(reg.descriptors), 2)

    def test_fingerprint_deterministic(self):
        reg = StrategyRegistry(descriptors=(_trend_long(), _range_revert()))
        reg2 = StrategyRegistry(descriptors=(_trend_long(), _range_revert()))
        self.assertEqual(reg.fingerprint, reg2.fingerprint)

    def test_fingerprint_changes_with_order(self):
        # Registry fingerprint should be order-dependent (tuple order matters)
        a = _trend_long()
        b = _range_revert()
        reg1 = StrategyRegistry(descriptors=(a, b))
        reg2 = StrategyRegistry(descriptors=(b, a))
        # Different order → different fingerprint
        self.assertNotEqual(reg1.fingerprint, reg2.fingerprint)

    def test_get_routable_filters_correctly(self):
        reg = StrategyRegistry(descriptors=(
            _trend_long(),         # formation_eligible → routable
            _range_revert(),       # frozen → routable
            _prototype_strategy(), # prototype → NOT routable
            _rejected_strategy(),  # rejected → NOT routable
            _disabled_strategy(),  # disabled → NOT routable
        ))
        routable = reg.get_routable()
        ids = {d.strategy_id for d in routable}
        self.assertIn("trend_long_v1", ids)
        self.assertIn("range_revert_v1", ids)
        self.assertNotIn("prototype_v1", ids)
        self.assertNotIn("rejected_v1", ids)
        self.assertNotIn("disabled_v1", ids)
        self.assertEqual(len(routable), 2)

    def test_get_by_id(self):
        reg = StrategyRegistry(descriptors=(_trend_long(), _range_revert()))
        results = reg.get_by_id("trend_long_v1")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].strategy_version, "1.0.0")

    def test_get_by_family(self):
        reg = StrategyRegistry(descriptors=(_trend_long(), _range_revert(), _downtrend_short()))
        trend = reg.get_by_family("trend_following")
        self.assertEqual(len(trend), 2)  # trend_long + downtrend_short

    def test_json_roundtrip(self):
        reg = StrategyRegistry(descriptors=(_trend_long(), _range_revert()))
        text = reg.to_json()
        reg2 = StrategyRegistry.from_json(text)
        self.assertEqual(reg.fingerprint, reg2.fingerprint)
        self.assertEqual(len(reg.descriptors), len(reg2.descriptors))

    def test_to_dict_roundtrip(self):
        reg = StrategyRegistry(descriptors=(_trend_long(), _range_revert()))
        d = reg.to_dict()
        reg2 = StrategyRegistry.from_dict(d)
        self.assertEqual(reg.fingerprint, reg2.fingerprint)


if __name__ == "__main__":
    unittest.main()
