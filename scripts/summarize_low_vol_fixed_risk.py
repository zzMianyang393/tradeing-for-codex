import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    j = json.loads(
        (root / "reports/low_volatility_drift_fixed_risk_audit.json").read_text(
            encoding="utf-8"
        )
    )
    agg = j.get("aggregate") or {}
    print("=== META ===")
    for k in (
        "report_type",
        "report_date",
        "status",
        "validated",
        "prospective_validation_required",
        "position_fraction",
        "max_positions",
        "scope",
        "source_status",
    ):
        if k in j:
            print(f"{k}: {j[k]}")
    print("safety_gates:", j.get("safety_gates"))
    print("positive_fold_count:", j.get("positive_fold_count"))
    print()
    print("=== AGGREGATE (portfolio) ===")
    for k, v in agg.items():
        if k in {"equity_curve", "closed_positions", "rejected_events"}:
            print(f"{k}: n={len(v) if hasattr(v, '__len__') else v}")
        else:
            print(f"{k}: {v}")
    print()
    print("=== FOLDS ===")
    folds = j.get("folds") or {}
    if isinstance(folds, dict):
        for name, f in folds.items():
            if not isinstance(f, dict):
                print(name, type(f))
                continue
            a = f.get("aggregate") if isinstance(f.get("aggregate"), dict) else f
            row = {
                "return_pct": a.get("total_return_pct"),
                "max_dd_pct": a.get("max_drawdown_pct"),
                "trades": a.get("accepted_positions"),
                "final_eq": a.get("final_equity"),
                "init_eq": a.get("initial_equity"),
                "win_rate": a.get("realized_win_rate"),
            }
            print(name, row)
    closed = agg.get("closed_positions") or []
    if not closed:
        return
    pnls = [float(t.get("realized_pnl") or 0) for t in closed]
    rets = [float(t.get("realized_return_pct") or 0) for t in closed]
    wins = sum(1 for p in pnls if p > 0)
    by_sym: dict[str, list] = defaultdict(lambda: [0, 0.0])
    by_dir: dict[str, list] = defaultdict(lambda: [0, 0.0])
    for t in closed:
        s = t.get("symbol") or "?"
        d = t.get("direction") or "?"
        p = float(t.get("realized_pnl") or 0)
        by_sym[s][0] += 1
        by_sym[s][1] += p
        by_dir[d][0] += 1
        by_dir[d][1] += p
    print()
    print("=== CLOSED TRADES ===")
    print("n", len(closed), "wins", wins, "win_rate", round(wins / len(closed), 4))
    print("sum_realized_pnl", round(sum(pnls), 2))
    print("avg_pnl", round(sum(pnls) / len(pnls), 2))
    print("avg_return_pct", round(sum(rets) / len(rets), 4) if rets else None)
    print("best_trade_pnl", round(max(pnls), 2), "worst", round(min(pnls), 2))
    print("by_direction", {k: {"n": v[0], "pnl": round(v[1], 2)} for k, v in by_dir.items()})
    top = sorted(by_sym.items(), key=lambda x: -x[1][1])[:10]
    bot = sorted(by_sym.items(), key=lambda x: x[1][1])[:5]
    print("top_symbols_by_pnl", [(k, v[0], round(v[1], 2)) for k, v in top])
    print("worst_symbols_by_pnl", [(k, v[0], round(v[1], 2)) for k, v in bot])
    by_m: dict[str, float] = defaultdict(float)
    for t in closed:
        ts = t.get("exit_ts") or t.get("entry_ts")
        if not ts:
            continue
        dt = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
        by_m[dt.strftime("%Y-%m")] += float(t.get("realized_pnl") or 0)
    months = sorted(by_m.items())
    pos_months = [m for m, p in months if p > 0]
    print("months", len(months), "positive_months", len(pos_months))
    if months:
        best_m = max(months, key=lambda x: x[1])
        pos_sum = sum(p for _, p in months if p > 0) or 1.0
        print("best_month", best_m, "share_of_gross_pos", round(best_m[1] / pos_sum, 4))
        print("first_month", months[0], "last_month", months[-1])
    print()
    print("eligible_symbols_count", len(j.get("eligible_symbols") or []))
    print("eligible_sample", (j.get("eligible_symbols") or [])[:12])


if __name__ == "__main__":
    main()
