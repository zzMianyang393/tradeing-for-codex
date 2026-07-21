from __future__ import annotations

from donchian_uptrend_capital_constrained_simulation import (
    compatible_long_events,
    formation_without_november,
    render_markdown,
)


def _event(direction: str, regime: str, split: str = "formation", month: str = "2024-10") -> dict:
    return {
        "direction": direction,
        "entry_regime": regime,
        "declared_compatible_regime": (direction == "long" and regime == "趋势上行")
        or (direction == "short" and regime == "趋势下行"),
        "split": split,
        "signal_timestamp_utc": f"{month}-01 00:00:00",
    }


def test_compatible_long_events_requires_long_uptrend_and_declared_match():
    source = {
        "events": [
            _event("long", "趋势上行"),
            _event("short", "趋势下行"),
            _event("long", "震荡"),
        ]
    }

    result = compatible_long_events(source)

    assert len(result) == 1
    assert result[0]["direction"] == "long"


def test_formation_without_november_is_fixed_stress_only():
    events = [
        _event("long", "趋势上行", "formation", "2024-10"),
        _event("long", "趋势上行", "formation", "2024-11"),
        _event("long", "趋势上行", "oos", "2025-01"),
    ]

    result = formation_without_november(events)

    assert len(result) == 1
    assert result[0]["signal_timestamp_utc"].startswith("2024-10")


def test_render_markdown_keeps_research_safety_closed():
    result = {
        "candidate_events": 20,
        "accepted_positions": 10,
        "capacity_rejected_events": 10,
        "total_return_pct": 1.0,
        "max_drawdown_pct": 5.0,
        "realized_win_rate": 0.5,
        "average_gross_exposure": 0.4,
        "peak_gross_exposure": 1.0,
        "top_positive_month_share": 0.2,
    }
    report = {
        "results": {
            "formation": result,
            "formation_excluding_2024_11": result,
            "oos": result,
        },
        "oos_screen_reasons": ["blocked"],
        "passes_diagnostic_screen": False,
    }

    document = render_markdown(report)

    assert "eligible_for_paper = false" in document
    assert "ready_for_combo_backtest = false" in document

