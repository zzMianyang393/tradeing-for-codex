from pathlib import Path
from types import SimpleNamespace

from prod.demo_execution_drill import (
    plan_demo_drill,
    run_demo_execution_drill,
)


def test_plan_blocks_rave_lab():
    for sym in ("RAVE-USDT-SWAP", "LAB-USDT-SWAP"):
        plan = plan_demo_drill(sym, confirm_smoke=True)
        assert plan.allowed is False
        assert plan.action == "blocked"


def test_plan_eth_readiness_vs_smoke():
    r = plan_demo_drill("ETH-USDT-SWAP", confirm_smoke=False)
    assert r.allowed and r.action == "readiness"
    s = plan_demo_drill("ETH", confirm_smoke=True)
    assert s.allowed and s.action == "smoke_limit_cancel" and s.symbol == "ETH-USDT-SWAP"


def test_run_drill_blocks_rave_without_network(tmp_path: Path):
    out = tmp_path / "drill.json"
    def _should_not_open() -> tuple:
        raise AssertionError("should not open exchange")

    report = run_demo_execution_drill(
        symbol="RAVE-USDT-SWAP",
        confirm_smoke=True,
        report_path=out,
        exchange_factory=_should_not_open,
    )
    assert report["formal_status"] == "blocked"
    assert out.exists()


def test_run_drill_readiness_with_stub_exchange(tmp_path: Path):
    class Stub:
        def get_account_balance(self):
            return SimpleNamespace(equity=1000.0, available_margin=900.0, used_margin=0.0)

        def get_ticker(self, symbol: str):
            return SimpleNamespace(symbol=symbol, last=3000.0, bid=2999.0, ask=3001.0)

        def get_positions(self):
            return []

        def place_order(self, *a, **k):
            raise AssertionError("readiness must not place orders")

        def cancel_order(self, *a, **k):
            raise AssertionError("readiness must not cancel")

    out = tmp_path / "ready.json"
    report = run_demo_execution_drill(
        symbol="ETH-USDT-SWAP",
        confirm_smoke=False,
        report_path=out,
        exchange_factory=lambda: (Stub(), None),
    )
    assert report["formal_status"] == "readiness_ok"
    assert report["order_submitted"] is False


def test_run_drill_smoke_with_stub_exchange(tmp_path: Path):
    calls = {"place": 0, "cancel": 0}

    class Stub:
        def get_account_balance(self):
            return SimpleNamespace(equity=1000.0, available_margin=900.0, used_margin=0.0)

        def get_ticker(self, symbol: str):
            return SimpleNamespace(symbol=symbol, last=3000.0, bid=2999.0, ask=3001.0)

        def get_positions(self):
            return []

        def place_order(self, symbol, direction, qty, order_type="market", price=None, fee=0.0):
            calls["place"] += 1
            assert symbol == "ETH-USDT-SWAP"
            assert order_type == "limit"
            assert price is not None and price < 3000
            return SimpleNamespace(order_id="oid-1", status="live")

        def cancel_order(self, symbol, order_id):
            calls["cancel"] += 1
            assert order_id == "oid-1"
            return {"code": "0"}

    out = tmp_path / "smoke.json"
    report = run_demo_execution_drill(
        symbol="ETH-USDT-SWAP",
        confirm_smoke=True,
        report_path=out,
        exchange_factory=lambda: (Stub(), None),
    )
    assert report["formal_status"] == "smoke_ok"
    assert calls == {"place": 1, "cancel": 1}


def test_missing_credentials_status(tmp_path: Path):
    report = run_demo_execution_drill(
        symbol="ETH-USDT-SWAP",
        confirm_smoke=False,
        report_path=tmp_path / "miss.json",
        exchange_factory=lambda: (None, {"error": "Missing OKX credentials: OKX_API_KEY"}),
    )
    assert report["formal_status"] == "blocked_missing_credentials"
