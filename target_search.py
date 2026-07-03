from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


TARGETS = {
    30: {"return_pct": 50.0, "win_rate": 0.68},
    7: {"return_pct": 20.0, "win_rate": 0.68},
}


def passes(results: dict[int, dict]) -> bool:
    for days, target in TARGETS.items():
        result = results[days]
        if not result.get("available"):
            return False
        if result["return_pct"] < target["return_pct"]:
            return False
        if result["win_rate"] < target["win_rate"]:
            return False
    return True


def score(results: dict[int, dict]) -> tuple[int, float, float, float]:
    hit = 0
    min_return_gap = 999.0
    min_win_gap = 999.0
    total_return = 0.0
    for days, target in TARGETS.items():
        result = results[days]
        ret_gap = result.get("return_pct", -999.0) - target["return_pct"]
        win_gap = result.get("win_rate", 0.0) - target["win_rate"]
        if ret_gap >= 0 and win_gap >= 0:
            hit += 1
        min_return_gap = min(min_return_gap, ret_gap)
        min_win_gap = min(min_win_gap, win_gap)
        total_return += result.get("return_pct", -999.0)
    return hit, min_return_gap, min_win_gap, total_return


def main() -> None:
    data_dir = Path("../Quantify/data")
    base = BacktestConfig()
    market = load_market(data_dir, base.timeframe_minutes)
    symbol_groups = [
        ("avx_apt_fil", ("AVAX-USDT-SWAP", "APT-USDT-SWAP", "FIL-USDT-SWAP")),
        ("avx_apt_fil_inj", ("AVAX-USDT-SWAP", "APT-USDT-SWAP", "FIL-USDT-SWAP", "INJ-USDT-SWAP")),
        ("avx_apt", ("AVAX-USDT-SWAP", "APT-USDT-SWAP")),
        ("avx_only", ("AVAX-USDT-SWAP",)),
        ("apt_only", ("APT-USDT-SWAP",)),
        ("recent_winners", ("AVAX-USDT-SWAP", "APT-USDT-SWAP", "FIL-USDT-SWAP", "INJ-USDT-SWAP", "XRP-USDT-SWAP")),
        ("trimmed_antigravity", ("AVAX-USDT-SWAP", "APT-USDT-SWAP", "FIL-USDT-SWAP", "INJ-USDT-SWAP", "LINK-USDT-SWAP")),
    ]
    regimes = [
        ("all", ("uptrend", "downtrend", "range", "transition")),
        ("no_transition", ("uptrend", "downtrend", "range")),
        ("trend_only", ("uptrend", "downtrend")),
        ("up_range", ("uptrend", "range")),
        ("down_range", ("downtrend", "range")),
    ]
    candidates = []
    for group_name, symbols in symbol_groups:
        group_market = {s: bars for s, bars in market.items() if s in symbols}
        if not group_market:
            continue
        for regime_name, enabled_regimes in regimes:
            for risk in (0.08, 0.112, 0.16, 0.22, 0.30):
                for tp in (0.75, 1.0, 1.17, 1.45, 1.8):
                    for stop in (1.7, 2.0, 2.36, 2.8):
                        for max_positions in (1, 2, 3):
                            cfg = replace(
                                base,
                                windows_days=(30, 7),
                                validation_target_win_rate=0.68,
                                risk_per_trade=risk,
                                take_profit_atr=tp,
                                stop_atr=stop,
                                trailing_atr=max(0.9, stop * 0.65),
                                max_positions=max_positions,
                                active_symbol_limit=len(symbols),
                                short_window_symbol_limit=len(symbols),
                                long_window_preferred_symbols=(),
                                enabled_regimes=enabled_regimes,
                            )
                            tester = Backtester(cfg)
                            results = {days: tester.run(group_market, days=days) for days in (30, 7)}
                            item = (score(results), group_name, regime_name, cfg, results)
                            candidates.append(item)
                            if passes(results):
                                print("FOUND")
                                print_result(item)
                                return
    candidates.sort(key=lambda item: item[0], reverse=True)
    for item in candidates[:25]:
        print_result(item)


def print_result(item) -> None:
    score_tuple, group_name, regime_name, cfg, results = item
    print(
        f"score={score_tuple} group={group_name} regimes={regime_name} "
        f"risk={cfg.risk_per_trade} tp={cfg.take_profit_atr} stop={cfg.stop_atr} "
        f"trail={cfg.trailing_atr} pos={cfg.max_positions}"
    )
    for days in (30, 7):
        r = results[days]
        print(
            f"  {days}d ret={r.get('return_pct', 0):.2f}% pnl={r.get('pnl', 0):.2f} "
            f"win={r.get('win_rate', 0) * 100:.2f}% tr={r.get('trades', 0)} "
            f"dd={r.get('max_drawdown_pct', 0):.2f}%"
        )


if __name__ == "__main__":
    main()
