from prod.admission import (
    AdmissionThresholds,
    admit_from_account_summary,
    equity_after_drop_max_winner,
    max_winner_share,
)


def test_max_winner_share():
    trades = [
        {"net_pnl": 10.0},
        {"net_pnl": 90.0},
        {"net_pnl": -5.0},
    ]
    assert abs(max_winner_share(trades) - 0.9) < 1e-9


def test_drop_max_winner_equity():
    trades = [
        {"net_pnl": 5.0},
        {"net_pnl": 100.0},
        {"net_pnl": -10.0},
    ]
    # 10 + 5 - 10 = 5 (skip +100)
    assert abs(equity_after_drop_max_winner(10.0, trades) - 5.0) < 1e-9


def test_admit_high_risk_with_concentration():
    account = {
        "trades": 8,
        "starting_equity": 10.0,
        "ending_equity": 200.0,
        "max_drawdown_fraction": 0.2,
        "profit_factor": 3.0,
        "permanent_account_state": "active_or_temporary_cooldown",
        "trades_detail": [
            {"net_pnl": 5.0},
            {"net_pnl": 200.0},  # ~95% of gross wins → hard concentration fail
            {"net_pnl": -10.0},
            {"net_pnl": 2.0},
            {"net_pnl": 1.0},
            {"net_pnl": 1.0},
            {"net_pnl": 1.0},
            {"net_pnl": 1.0},
        ],
    }
    rejected = admit_from_account_summary(
        strategy_id="s",
        track="ten_u_high_risk",
        account=account,
        high_risk_sleeve=True,
        accept_concentration_risk=False,
    )
    assert rejected.paper_prep_allowed is False
    assert "max_winner_share_above_hard_threshold" in rejected.reasons

    accepted = admit_from_account_summary(
        strategy_id="s",
        track="ten_u_high_risk",
        account=account,
        high_risk_sleeve=True,
        accept_concentration_risk=True,
    )
    assert accepted.paper_prep_allowed is True
    assert accepted.live_allowed is False
    assert accepted.operator_flags["prospective_wait_required"] is False


def test_admit_fails_low_trades():
    account = {
        "trades": 2,
        "starting_equity": 10.0,
        "ending_equity": 50.0,
        "max_drawdown_fraction": 0.1,
        "profit_factor": 2.0,
        "permanent_account_state": "active_or_temporary_cooldown",
        "trades_detail": [{"net_pnl": 20.0}, {"net_pnl": 20.0}],
    }
    result = admit_from_account_summary(
        strategy_id="s",
        track="t",
        account=account,
        thresholds=AdmissionThresholds(minimum_trades=6),
        high_risk_sleeve=True,
        accept_concentration_risk=True,
    )
    assert result.paper_prep_allowed is False
    assert "trades_below_minimum" in result.reasons
