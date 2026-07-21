"""Tests for strategy_prototype_universe.py."""

from __future__ import annotations

import pytest

from strategy_prototype_universe import (
    PROTOTYPES,
    StrategyPrototype,
    get_prototype_by_id,
    get_prototypes,
    get_prototypes_by_family,
)


class TestPrototypeStructure:
    def test_minimum_count(self):
        assert len(PROTOTYPES) >= 30

    def test_required_fields(self):
        for p in PROTOTYPES:
            assert p.strategy_id
            assert p.name_cn
            assert p.family
            assert p.expected_hold_days > 0
            assert p.expected_events_per_month > 0
            assert p.executed_legs in (2, 4)
            assert isinstance(p.required_data, list)
            assert len(p.required_data) > 0

    def test_unique_ids(self):
        ids = [p.strategy_id for p in PROTOTYPES]
        assert len(ids) == len(set(ids))


class TestFamilies:
    def test_all_required_families_present(self):
        families = set(p.family for p in PROTOTYPES)
        required = {
            "trend_following", "mean_reversion", "breakout",
            "funding_carry", "oi_leverage", "cross_asset",
            "grid_martingale", "event_news", "machine_learning",
            "hft_microstructure",
        }
        assert required.issubset(families), f"Missing: {required - families}"

    def test_trend_following_count(self):
        trends = get_prototypes_by_family("trend_following")
        assert len(trends) >= 3

    def test_grid_martingale_uses_flag(self):
        for p in get_prototypes_by_family("grid_martingale"):
            assert p.uses_grid_or_martingale

    def test_event_news_uses_external(self):
        for p in get_prototypes_by_family("event_news"):
            assert p.uses_external_data

    def test_hft_uses_orderbook(self):
        for p in get_prototypes_by_family("hft_microstructure"):
            assert p.uses_hft_or_orderbook


class TestLookup:
    def test_get_by_id(self):
        p = get_prototype_by_id("daily_donchian55_trend")
        assert p is not None
        assert p.family == "trend_following"

    def test_get_by_id_missing(self):
        assert get_prototype_by_id("nonexistent_id") is None

    def test_get_by_family(self):
        trends = get_prototypes_by_family("trend_following")
        assert all(p.family == "trend_following" for p in trends)


class TestSerialization:
    def test_to_dict(self):
        p = PROTOTYPES[0]
        d = p.to_dict()
        assert isinstance(d, dict)
        assert d["strategy_id"] == p.strategy_id
        assert d["expected_hold_days"] == p.expected_hold_days
