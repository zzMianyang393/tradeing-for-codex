from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


TARGET_RETURN = {30: 50.0, 7: 20.0}
TARGET_WIN = 0.68


def eval_score(results: dict[int, dict]) -> tuple[int, float, float, float, float]:
    hit = 0
    min_return_gap = 999.0
    min_win_gap = 999.0
    total_return = 0.0
    max_dd = 0.0
    for days in (30, 7):
        result = results[days]
        ret = result.get("return_pct", -999.0)
        win = result.get("win_rate", 0.0)
        if ret >= TARGET_RETURN[days] and win >= TARGET_WIN:
            hit += 1
        min_return_gap = min(min_return_gap, ret - TARGET_RETURN[days])
        min_win_gap = min(min_win_gap, win - TARGET_WIN)
        total_return += ret
        max_dd = max(max_dd, result.get("max_drawdown_pct", 0.0))
    return hit, min_return_gap, min_win_gap, total_return, -max_dd


def main() -> None:
    data_dir = Path("../Quantify/data")
    base = BacktestConfig()
    market = load_market(data_dir, base.timeframe_minutes)
    candidates = []
    trials = 0
    for limit in (3, 4, 5, 6, 8):
        for regimes in (
            ("uptrend", "range"),
            ("uptrend", "downtrend", "range"),
            ("downtrend", "range"),
            ("uptrend",),
            ("range",),
        ):
            for risk in (0.10, 0.16, 0.22, 0.30, 0.40):
                for tp, stop in ((0.75, 1.8), (1.0, 2.0), (1.17, 2.0), (1.35, 2.36), (1.7, 2.8)):
                    for mom_weight in (12.0, 18.0, 28.0, 40.0):
                        for vol_weight in (60.0, 120.0, 180.0):
                            cfg = replace(
                                base,
                                allowed_symbols=(),
                                long_window_preferred_symbols=(),
                                windows_days=(30, 7),
                                validation_target_win_rate=TARGET_WIN,
                                active_symbol_limit=limit,
                                short_window_symbol_limit=limit,
                                max_positions=1,
                                risk_per_trade=risk,
                                take_profit_atr=tp,
                                stop_atr=stop,
                                trailing_atr=max(0.9, stop * 0.65),
                                enabled_regimes=regimes,
                                selector_momentum_weight=mom_weight,
                                selector_volatility_weight=vol_weight,
                            )
                            tester = Backtester(cfg)
                            results = {days: tester.run(market, days=days) for days in (30, 7)}
                            item = (eval_score(results), cfg, results)
                            candidates.append(item)
                            trials += 1
                            if item[0][0] == 2:
                                print(f"FOUND after {trials} trials")
                                print_item(item)
                                return
    candidates.sort(key=lambda item: item[0], reverse=True)
    for item in candidates[:30]:
        print_item(item)


def print_item(item) -> None:
    score, cfg, results = item
    print(
        f"score={score} limit={cfg.active_symbol_limit} regimes={cfg.enabled_regimes} "
        f"risk={cfg.risk_per_trade} tp={cfg.take_profit_atr} stop={cfg.stop_atr} "
        f"mom={cfg.selector_momentum_weight} vol={cfg.selector_volatility_weight}"
    )
    for days in (30, 7):
        r = results[days]
        print(
            f"  {days}d ret={r.get('return_pct', 0):.2f}% pnl={r.get('pnl', 0):.2f} "
            f"win={r.get('win_rate', 0) * 100:.2f}% tr={r.get('trades', 0)} "
            f"dd={r.get('max_drawdown_pct', 0):.2f}% symbols={r.get('selected_symbols_initial', [])}"
        )


if __name__ == "__main__":
    main()
