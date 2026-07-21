from __future__ import annotations

from pathlib import Path


CARD = Path("docs/downtrend_rebound_combo_research_card_2026-07-13.md")


def test_downtrend_rebound_combo_card_exists():
    assert CARD.exists()


def test_downtrend_rebound_combo_card_keeps_safety_gates_closed():
    content = CARD.read_text(encoding="utf-8")

    assert "approved_for_paper = []" in content
    assert "eligible_for_paper = false" in content
    assert "safe_to_enable_trading = false" in content
    assert "ready_for_combo_backtest = false" in content


def test_downtrend_rebound_combo_card_registers_fixed_hypotheses():
    content = CARD.read_text(encoding="utf-8")

    assert "H1: RSI Primary, Donchian Veto" in content
    assert "H2: RSI Primary, EMA Confirmation" in content
    assert "H3: RSI Standalone Bucket Baseline" in content
    assert "Do not change RSI(14), threshold 35, recovery 50, or max 10-day hold." in content


def test_downtrend_rebound_combo_card_requires_future_window_validation():
    content = CARD.read_text(encoding="utf-8")

    assert "future-window validation" in content
    assert "cannot be promoted using only the current OOS window" in content


def test_downtrend_rebound_combo_card_forbids_runner_and_optimizers():
    content = CARD.read_text(encoding="utf-8")

    assert "Any implementation imports or calls `runner.py`" in content
    assert "no runner integration" in content
    assert "no dynamic weight optimizer" in content
