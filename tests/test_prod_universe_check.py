from prod.universe_check import (
    build_symbol_row,
    classify_demo_tradeability,
    run_universe_check,
)


def test_classify_demo_known_gap():
    flag, reason = classify_demo_tradeability("RAVE-USDT-SWAP")
    assert flag == "no"
    assert "demo_gap" in reason or "gap" in reason


def test_classify_demo_major_unverified():
    flag, reason = classify_demo_tradeability("BTC-USDT-SWAP")
    assert flag == "unknown_requires_keys"


def test_build_row_live_present():
    live = {
        "instId": "ETH-USDT-SWAP",
        "state": "live",
        "ctVal": "0.1",
        "minSz": "0.01",
        "lever": "100",
    }
    row = build_symbol_row("ETH-USDT-SWAP", live, roles=["ten_u_v2", "demo_execution_drill"])
    assert row.live_present is True
    assert row.live_state == "live"
    assert row.paper_local_ok is True


def test_run_universe_check_with_stub_fetcher():
    catalog = {
        "RAVE-USDT-SWAP": {
            "instId": "RAVE-USDT-SWAP",
            "state": "live",
            "ctVal": "10",
            "minSz": "0.01",
            "lever": "20",
        },
        "LAB-USDT-SWAP": {
            "instId": "LAB-USDT-SWAP",
            "state": "live",
            "ctVal": "10",
            "minSz": "0.1",
            "lever": "10",
        },
        "ETH-USDT-SWAP": {
            "instId": "ETH-USDT-SWAP",
            "state": "live",
            "ctVal": "0.1",
            "minSz": "0.01",
            "lever": "100",
        },
        "BTC-USDT-SWAP": {
            "instId": "BTC-USDT-SWAP",
            "state": "live",
            "ctVal": "0.01",
            "minSz": "0.01",
            "lever": "100",
        },
    }

    def fetcher(symbol: str):
        return catalog.get(symbol)

    report = run_universe_check(instrument_fetcher=fetcher)
    assert report["ten_u_live_all_present"] is True
    by_sym = {r["symbol"]: r for r in report["symbols"]}
    assert by_sym["RAVE-USDT-SWAP"]["live_present"] is True
    assert by_sym["RAVE-USDT-SWAP"]["demo_tradeable"] == "no"
    assert by_sym["LAB-USDT-SWAP"]["demo_tradeable"] == "no"
    assert by_sym["ETH-USDT-SWAP"]["live_state"] == "live"
