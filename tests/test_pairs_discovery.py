from __future__ import annotations

import pandas as pd

from pairs_discovery import benjamini_hochberg, discover_from_panel


def test_benjamini_hochberg_rejects_unadjusted_borderline_values():
    accepted = benjamini_hochberg({"a": 0.001, "b": 0.04, "c": 0.9}, q=0.05)
    assert accepted == {"a"}


def test_benjamini_hochberg_respects_the_full_discovery_universe():
    accepted = benjamini_hochberg({"a": 0.001, "b": 0.01}, q=0.05, total_hypotheses=100)
    assert accepted == set()


def test_discovery_uses_only_requested_formation_tail():
    index = pd.date_range("2026-01-01", periods=40, freq="15min")
    panel = pd.DataFrame({"A-USDT-SWAP": range(1, 41), "B-USDT-SWAP": range(2, 42)}, index=index)
    discoveries = discover_from_panel(panel, formation_bars=30, fdr_q=0.05, max_half_life_bars=9999)
    assert len(discoveries) == 1
    assert discoveries[0].statistics.observations == 30
