from __future__ import annotations

from downtrend_bidirectional_drawdown_anatomy_audit import (
    build_report,
    daily_equity_changes,
    episode_attribution,
    maximum_drawdown_episode,
)


DAY_MS = 24 * 60 * 60 * 1000


def _point(day: int, equity: float, net: float = 0.0) -> dict:
    return {
        "ts": day * DAY_MS,
        "equity": equity,
        "active_long_positions": 1,
        "active_short_positions": 1,
        "long_exposure": 0.4,
        "short_exposure": 0.4 - net,
        "net_directional_exposure": net,
        "component_exposure": {"long": 0.4, "short": 0.4 - net},
    }


def test_maximum_drawdown_episode_finds_peak_and_trough():
    curve = [_point(1, 110.0), _point(2, 120.0), _point(3, 90.0), _point(4, 100.0)]

    episode = maximum_drawdown_episode(curve, 100.0)

    assert episode["peak_ts"] == 2 * DAY_MS
    assert episode["trough_ts"] == 3 * DAY_MS
    assert episode["drawdown_pct"] == 25.0


def test_daily_equity_changes_include_exposure_state():
    changes = daily_equity_changes([_point(1, 90.0, 0.2)], 100.0)

    assert changes[0]["equity_change_pct"] == -10.0
    assert changes[0]["net_directional_exposure"] == 0.2


def test_episode_attribution_groups_component_pnl():
    result = {
        "equity_curve": [_point(1, 110.0), _point(2, 90.0)],
        "closed_positions": [
            {
                "entry_ts": DAY_MS,
                "exit_ts": 2 * DAY_MS,
                "component_id": "rsi",
                "direction": "long",
                "realized_pnl": -100.0,
            }
        ],
    }
    episode = maximum_drawdown_episode(result["equity_curve"], 100.0)

    attribution = episode_attribution(result, episode)

    assert attribution["realized_pnl_by_component"]["rsi"] == -100.0
    assert attribution["overlapping_position_count"] == 1


def test_build_report_keeps_safety_closed():
    combo = {
        "research_id": "combo",
        "results": {
            "oos": {
                "initial_equity": 100.0,
                "total_return_pct": 1.0,
                "equity_curve": [_point(1, 101.0)],
                "closed_positions": [],
                "rejected_events": [],
            }
        },
    }

    report = build_report(combo)

    assert report["scope"] == "read_only_drawdown_diagnostic_not_risk_overlay_test"
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["eligible_for_paper"] is False
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False

