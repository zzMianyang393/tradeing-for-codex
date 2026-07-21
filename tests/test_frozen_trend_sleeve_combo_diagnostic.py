from frozen_trend_sleeve_combo_diagnostic import COMPONENT_CAPS, diagnostic_reasons, is_compatible, run, tag_events


def test_component_compatibility_keeps_only_declared_regime_events():
    assert is_compatible("daily_parabolic_sar_trend", {"direction": "long", "entry_regime": "趋势上行"})
    assert not is_compatible("daily_parabolic_sar_trend", {"direction": "long", "entry_regime": "震荡"})
    assert is_compatible("donchian_atr_trend_baseline", {"declared_compatible_regime": True})
    assert not is_compatible("4h_ema_crossover", {"direction_compatible_regime": False})


def test_tagged_events_have_frozen_component_priorities():
    sources = {
        "daily_parabolic_sar_trend": {"events": [{"entry_ts": 2, "symbol": "BTC", "direction": "long", "entry_regime": "趋势上行"}]},
        "donchian_atr_trend_baseline": {"events": [{"entry_ts": 1, "symbol": "ETH", "declared_compatible_regime": True}]},
        "4h_ema_crossover": {"events": [{"entry_ts": 3, "symbol": "SOL", "direction_compatible_regime": True}]},
    }
    tagged = tag_events(sources)

    assert [event["component_id"] for event in tagged] == ["donchian_atr_trend_baseline", "daily_parabolic_sar_trend", "4h_ema_crossover"]
    assert COMPONENT_CAPS == {"daily_parabolic_sar_trend": 3, "donchian_atr_trend_baseline": 1, "4h_ema_crossover": 1}


def test_diagnostic_reasons_reject_bad_oos_result():
    reasons = diagnostic_reasons({"accepted_positions": 19, "total_return_pct": -1.0, "max_drawdown_pct": 21.0, "top_positive_month_share": 0.3})

    assert len(reasons) == 4


def test_run_uses_caller_supplied_price_map(monkeypatch):
    event = {
        "symbol": "BTC", "direction": "long", "entry_ts": 1, "exit_ts": 2,
        "entry_price": 1.0, "exit_price": 1.0, "component_id": "daily_parabolic_sar_trend",
    }
    captured = {}

    def fake_simulate(events, prices, **_kwargs):
        captured["prices"] = prices
        return {"candidate_events": 0, "accepted_positions": 0, "capacity_rejected_events": 0,
                "total_return_pct": 0.0, "max_drawdown_pct": 0.0, "realized_win_rate": 0.0,
                "average_gross_exposure": 0.0, "peak_gross_exposure": 0.0, "capital_turnover": 0.0,
                "top_positive_month_share": 0.0, "closed_positions": [], "rejected_events": [], "initial_equity": 1.0}

    monkeypatch.setattr("frozen_trend_sleeve_combo_diagnostic.simulate_portfolio", fake_simulate)
    run([event], {"BTC": {}})

    assert captured["prices"] == {"BTC": {}}
