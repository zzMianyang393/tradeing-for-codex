"""Tests for 1h research batch v5."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import _funding_allows
from prod.research_batch_majors_v5 import research_catalog_v5, run_majors_research_batch_v5


class _B:
    def __init__(self, funding_rate):
        self.funding_rate = funding_rate


def test_funding_allows_gates():
    assert _funding_allows(_B(0.01), -1, "short_funding_positive") is True
    assert _funding_allows(_B(-0.01), -1, "short_funding_positive") is False
    assert _funding_allows(_B(-0.01), -1, "short_funding_negative") is True
    assert _funding_allows(_B(None), -1, "short_funding_positive") is False
    assert _funding_allows(_B(0.01), -1, "none") is True


def test_v5_catalog():
    cat = research_catalog_v5()
    assert len(cat) >= 10
    assert all(c["config"].timeframe_minutes == 60 for c in cat)
    assert any(c.get("funding_filter") != "none" for c in cat)


def test_v5_batch_if_data():
    data = Path("data")
    if not (data / "BTC_1h.csv").exists() or not (data / "ETH_1h.csv").exists():
        pytest.skip("1h data missing")
    report = run_majors_research_batch_v5(data, max_bars=3000, start_equity=10.0)
    assert report["formal_status"] == "ok"
    assert report["candidate_count"] >= 10
    assert report["places_exchange_orders"] is False
