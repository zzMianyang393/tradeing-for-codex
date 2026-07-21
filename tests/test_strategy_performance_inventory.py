from strategy_performance_inventory import equity_sharpe, event_sharpe, metrics


def test_event_sharpe_is_explicitly_nonannualized():
    report = {"events": [{"split": "formation", "net_return_pct": 1.0}, {"split": "formation", "net_return_pct": 2.0}], "formation": {"events": 2, "net_sum_pct": 3.0, "mean_pct": 1.5, "win_rate": 1.0}}
    value = metrics(report)["formation"]
    assert value["sharpe_type"] == "event_return_nonannualized"
    assert value["basis"] == "additive_event_returns_not_portfolio_equity"


def test_equity_sharpe_uses_daily_returns_only():
    assert equity_sharpe([{"ts": 0, "equity": 100.0}, {"ts": 86_400_000, "equity": 101.0}, {"ts": 172_800_000, "equity": 102.0}]) is not None
    assert equity_sharpe([{"equity": 100.0}, {"equity": 101.0}]) is None
    assert event_sharpe([], "oos") is None


def test_portfolio_metrics_preserve_drawdown_and_do_not_fake_missing_sharpe():
    report = {"aggregate": {"accepted_positions": 2, "total_return_pct": -3.0, "max_drawdown_pct": 8.0, "realized_win_rate": 0.5}}
    value = metrics(report)["aggregate"]
    assert value["net_result_pct"] == -3.0
    assert value["max_drawdown_pct"] == 8.0
    assert value["sharpe"] is None and value["sharpe_type"] == "not_available"


def test_nested_net_and_shared_capital_structures_are_extracted_without_conflation():
    carry = {"summary": {"formation": {"net": {"observations": 4, "sum_pct": -0.4, "mean_pct": -0.1, "win_rate": 0.0}}}}
    combo = {"shared_capital_combo": {"aggregate": {"accepted_positions": 5, "total_return_pct": -2.0, "max_drawdown_pct": 3.0, "realized_win_rate": 0.4}}}
    assert metrics(carry)["formation"]["net_result_pct"] == -0.4
    assert metrics(combo)["aggregate"]["max_drawdown_pct"] == 3.0


def test_regime_summary_uses_declared_compatible_bucket_before_all_events():
    report = {"summary": {"formation": {"all_events": {"all": {"observations": 99, "mean_pct": 9.0}}, "declared_compatible_regime": {"all": {"observations": 3, "mean_pct": -2.0, "win_rate": 0.0}}}}}
    value = metrics(report)["formation"]
    assert value["events"] == 3
    assert value["net_result_pct"] == -6.0
    assert value["basis"] == "event_audit_declared_compatible_regime"
