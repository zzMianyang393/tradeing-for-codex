from __future__ import annotations

from ema_short_downtrend_capital_constrained_simulation import (
    compatible_short_events,
    diagnostic_reasons,
    formation_without_november,
    render_markdown,
)


def _event(direction: str, regime: str, month: str = "2024-10", split: str = "formation") -> dict:
    return {
        "direction": direction,
        "entry_regime": regime,
        "direction_compatible_regime": (direction == "short" and regime == "趋势下行")
        or (direction == "long" and regime == "趋势上行"),
        "signal_timestamp_utc": f"{month}-01 00:00:00",
        "split": split,
    }


def _result(return_pct: float = 1.0, accepted: int = 20, drawdown: float = 5.0, concentration: float = 0.2) -> dict:
    return {
        "candidate_events": accepted,
        "accepted_positions": accepted,
        "capacity_rejected_events": 0,
        "total_return_pct": return_pct,
        "max_drawdown_pct": drawdown,
        "realized_win_rate": 0.5,
        "average_gross_exposure": 0.4,
        "peak_gross_exposure": 1.0,
        "top_positive_month_share": concentration,
    }


def test_compatible_short_events_requires_direction_and_regime_match():
    source = {
        "events": [
            _event("short", "趋势下行"),
            _event("long", "趋势上行"),
            _event("short", "震荡"),
        ]
    }

    result = compatible_short_events(source)

    assert len(result) == 1
    assert result[0]["direction"] == "short"


def test_formation_without_november_is_fixed_stress():
    events = [
        _event("short", "趋势下行", "2024-10"),
        _event("short", "趋势下行", "2024-11"),
        _event("short", "趋势下行", "2025-01", "oos"),
    ]

    result = formation_without_november(events)

    assert len(result) == 1
    assert result[0]["signal_timestamp_utc"].startswith("2024-10")


def test_diagnostic_reasons_require_stability_in_both_windows():
    reasons = diagnostic_reasons(_result(-1.0), _result(1.0), _result(2.0))

    assert "formation total return <= 0" in reasons


def test_render_markdown_keeps_safety_closed():
    result = _result()
    report = {
        "results": {
            "formation": result,
            "formation_excluding_2024_11": result,
            "oos": result,
        },
        "diagnostic_reasons": ["blocked"],
        "passes_diagnostic_screen": False,
    }

    document = render_markdown(report)

    assert "eligible_for_paper = false" in document
    assert "ready_for_combo_backtest = false" in document

