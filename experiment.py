from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from backtester import Backtester
from config import BacktestConfig
from market import load_market


def objective(results: list[dict]) -> tuple[int, float, float, float]:
    passes = sum(1 for r in results if r.get("target_pass"))
    worst_pnl = min(float(r.get("pnl", -9999.0)) for r in results)
    worst_win = min(float(r.get("win_rate", 0.0)) for r in results)
    total_pnl = sum(float(r.get("pnl", 0.0)) for r in results)
    return passes, worst_pnl, worst_win, total_pnl


def main() -> None:
    data_dir = Path("../Quantify/data")
    base = BacktestConfig()
    market = load_market(data_dir, base.timeframe_minutes)
    candidates = []
    for invert in (False, True):
        for min_score in (2.4, 2.9, 3.4):
            for tp in (0.65, 1.15):
                for stop in (1.6, 2.6):
                    for lookback, pause in ((12, 192),):
                        cfg = replace(
                            base,
                            invert_signals=invert,
                            min_score=min_score,
                            take_profit_atr=tp,
                            stop_atr=stop,
                            trailing_atr=max(0.8, stop * 0.75),
                            edge_lookback_trades=lookback,
                            edge_pause_bars=pause,
                        )
                        tester = Backtester(cfg)
                        results = [tester.run(market, days=days) for days in (365, 180, 90)]
                        item = (objective(results), cfg, results)
                        candidates.append(item)
                        score = item[0]
                        print(
                            f"trial pass={score[0]}/3 worst_pnl={score[1]:.4f} worst_win={score[2]:.2%} "
                            f"invert={cfg.invert_signals} score={cfg.min_score} tp={cfg.take_profit_atr} stop={cfg.stop_atr}",
                            flush=True,
                        )
    candidates.sort(key=lambda item: item[0], reverse=True)
    for rank, (score, cfg, results) in enumerate(candidates[:30], start=1):
        print(
            f"#{rank:02d} pass={score[0]}/6 worst_pnl={score[1]:.4f} worst_win={score[2]:.2%} total={score[3]:.4f} "
            f"invert={cfg.invert_signals} score={cfg.min_score} tp={cfg.take_profit_atr} stop={cfg.stop_atr} "
            f"edge=({cfg.edge_lookback_trades},{cfg.edge_pause_bars})"
        )
        print(
            "    "
            + " | ".join(
                f"{r['days']}d pnl={r.get('pnl',0):.3f} win={r.get('win_rate',0)*100:.1f}% tr={r.get('trades',0)}"
                for r in results
            )
        )


if __name__ == "__main__":
    main()
