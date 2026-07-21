"""Tests for strategy_preflight_review.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from strategy_preflight_review import review_prototype, run_review
from strategy_prototype_universe import StrategyPrototype, get_prototype_by_id


# ── Mock data ────────────────────────────────────────────────────────────────

MOCK_RISK_MAP = {
    "cost_constraints": {
        "single_market_round_trip_cost": 0.0016,
        "two_market_round_trip_cost": 0.0032,
    },
    "turnover_constraints": {
        "thresholds": {
            "min_hold_days": 3.0,
            "max_events_per_month": 12,
        }
    },
    "trading_permission": {
        "approved_for_paper": [],
        "safe_to_enable_trading": False,
    },
}

MOCK_REJECTED_IDS = {"donchian_atr_trend_baseline", "pairs_walk_forward", "spot_perp_basis"}
MOCK_INVALID_IDS = {"funding_oi_joint_original"}


# ── Grid / martingale → risk_blocked ─────────────────────────────────────────

class TestGridMartingaleRiskBlocked:
    def test_grid_is_risk_blocked(self):
        proto = get_prototype_by_id("grid_trading")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "risk_blocked"

    def test_martingale_is_risk_blocked(self):
        proto = get_prototype_by_id("martingale_loss_add")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "risk_blocked"

    def test_locking_is_risk_blocked(self):
        proto = get_prototype_by_id("locking_hedge")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "risk_blocked"


# ── HFT / orderbook → data_blocked ───────────────────────────────────────────

class TestHftDataBlocked:
    def test_orderbook_is_data_blocked(self):
        proto = get_prototype_by_id("orderbook_imbalance")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "data_blocked"

    def test_tick_is_data_blocked(self):
        proto = get_prototype_by_id("tick_momentum")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "data_blocked"

    def test_liquidation_is_data_blocked(self):
        proto = get_prototype_by_id("liquidation_cascade")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "data_blocked"


# ── News / macro → data_blocked ──────────────────────────────────────────────

class TestNewsDataBlocked:
    def test_news_is_data_blocked(self):
        proto = get_prototype_by_id("news_sentiment_trade")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "data_blocked"

    def test_macro_is_data_blocked(self):
        proto = get_prototype_by_id("macro_event_trade")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "data_blocked"


# ── Duplicate rejected ───────────────────────────────────────────────────────

class TestDuplicateRejected:
    def test_exact_rejected_id_is_duplicate(self):
        proto = StrategyPrototype(
            strategy_id="daily_ma_alignment",
            name_cn="test",
            family="trend_following",
            expected_hold_days=10,
            expected_events_per_month=3,
            executed_legs=2,
            required_data=["ohlcv_daily"],
        )
        result = review_prototype(proto, MOCK_RISK_MAP, {"daily_ma_alignment"}, MOCK_INVALID_IDS)
        assert result["status"] == "duplicate_rejected"

    def test_resembles_rejected_is_duplicate(self):
        proto = get_prototype_by_id("daily_donchian55_trend")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "duplicate_rejected"

    def test_resembles_invalid_is_duplicate(self):
        # Create a test prototype that resembles an invalid one
        proto = StrategyPrototype(
            strategy_id="test_invalid_overlap",
            name_cn="test",
            family="test",
            expected_hold_days=10,
            expected_events_per_month=3,
            executed_legs=2,
            required_data=["ohlcv_daily"],
            resembles_rejected=["funding_oi_joint_original"],
        )
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "duplicate_rejected"

    def test_unmatched_resemblance_label_is_duplicate(self):
        proto = StrategyPrototype(
            strategy_id="test_family_overlap",
            name_cn="test",
            family="trend_following",
            expected_hold_days=10,
            expected_events_per_month=3,
            executed_legs=2,
            required_data=["ohlcv_daily"],
            resembles_rejected=["multi_timeframe"],
        )
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "duplicate_rejected"
        assert "multi_timeframe" in result["reasons"][0]


# ── OI/leverage → meta_only ──────────────────────────────────────────────────

class TestOiLeverageMetaOnly:
    def test_oi_divergence_is_meta_only(self):
        proto = get_prototype_by_id("oi_divergence_signal")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "meta_only"

    def test_oi_extreme_is_meta_only(self):
        proto = get_prototype_by_id("oi_extreme_crowding")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "meta_only"


# ── Turnover checks ──────────────────────────────────────────────────────────

class TestTurnoverChecks:
    def test_short_hold_rejected_by_turnover(self):
        proto = StrategyPrototype(
            strategy_id="test_short_hold",
            name_cn="test",
            family="test",
            expected_hold_days=1,
            expected_events_per_month=5,
            executed_legs=2,
            required_data=["ohlcv_15m"],
        )
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "rejected_by_turnover"

    def test_high_events_rejected_by_turnover(self):
        proto = StrategyPrototype(
            strategy_id="test_high_events",
            name_cn="test",
            family="test",
            expected_hold_days=5,
            expected_events_per_month=20,
            executed_legs=2,
            required_data=["ohlcv_15m"],
        )
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "rejected_by_turnover"


# ── Eligible prototype ───────────────────────────────────────────────────────

class TestEligiblePrototype:
    def test_low_turnover_trend_can_be_eligible(self):
        """A trend prototype with no rejected overlap and proper turnover should be eligible."""
        proto = StrategyPrototype(
            strategy_id="test_eligible_trend",
            name_cn="test eligible trend",
            family="trend_following",
            expected_hold_days=14,
            expected_events_per_month=3,
            executed_legs=2,
            required_data=["ohlcv_daily"],
        )
        result = review_prototype(proto, MOCK_RISK_MAP, set(), set())
        assert result["status"] == "eligible_for_research"


# ── ML → frozen ──────────────────────────────────────────────────────────────

class TestMlFrozen:
    def test_ml_is_frozen(self):
        proto = get_prototype_by_id("ml_price_prediction")
        assert proto is not None
        result = review_prototype(proto, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
        assert result["status"] == "frozen"


# ── Safety gates ─────────────────────────────────────────────────────────────

class TestSafetyGates:
    def test_approved_for_paper_empty(self, tmp_path):
        """approved_for_paper must remain empty in the review output."""
        # Write mock files
        rm_path = tmp_path / "risk_map.json"
        rm_path.write_text(json.dumps(MOCK_RISK_MAP), encoding="utf-8")
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps({
            "records": [],
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
        }), encoding="utf-8")

        result = run_review(rm_path, reg_path)
        assert result["safety_gates"]["approved_for_paper"] == []
        assert result["safety_gates"]["safe_to_enable_trading"] is False

    def test_registry_top_level_safety_gates_are_authoritative(self, tmp_path):
        rm_path = tmp_path / "risk_map.json"
        rm_path.write_text(json.dumps(MOCK_RISK_MAP), encoding="utf-8")
        reg_path = tmp_path / "registry.json"
        reg_path.write_text(json.dumps({
            "records": [],
            "approved_for_paper": ["paper_only_smoke_test"],
            "safe_to_enable_trading": False,
        }), encoding="utf-8")

        result = run_review(rm_path, reg_path)
        assert result["safety_gates"]["approved_for_paper"] == ["paper_only_smoke_test"]
        assert result["safety_gates"]["safe_to_enable_trading"] is False


# ── Risk blocked / data blocked not eligible ─────────────────────────────────

class TestBlockedNotEligible:
    def test_risk_blocked_never_eligible(self):
        for p in [get_prototype_by_id("grid_trading"), get_prototype_by_id("martingale_loss_add")]:
            assert p is not None
            result = review_prototype(p, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
            assert result["status"] != "eligible_for_research"

    def test_data_blocked_never_eligible(self):
        for p in [get_prototype_by_id("orderbook_imbalance"), get_prototype_by_id("news_sentiment_trade")]:
            assert p is not None
            result = review_prototype(p, MOCK_RISK_MAP, MOCK_REJECTED_IDS, MOCK_INVALID_IDS)
            assert result["status"] != "eligible_for_research"
