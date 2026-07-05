from __future__ import annotations


def audit_report(
    report: dict,
    required_windows: tuple[int, ...] = (365, 180, 90, 60, 30, 7),
    min_win_rate: float = 0.60,
    min_pnl: float = 0.0,
    min_pnl_by_window: dict[int, float] | None = None,
    min_return_by_window: dict[int, float] | None = None,
) -> dict:
    failures: list[str] = []
    windows = report.get("windows", {})

    for days in required_windows:
        key = str(days)
        result = windows.get(key)
        if result is None:
            failures.append(f"{days}d missing")
            continue
        if not result.get("available"):
            failures.append(f"{days}d unavailable")
            continue
        pnl = float(result.get("pnl", 0.0))
        return_pct = float(result.get("return_pct", 0.0))
        win_rate = float(result.get("win_rate", 0.0))
        window_min_pnl = (min_pnl_by_window or {}).get(days, min_pnl)
        min_return = (min_return_by_window or {}).get(days)
        if pnl <= window_min_pnl:
            failures.append(f"{days}d pnl {pnl:g} <= {window_min_pnl:g}")
        if min_return is not None and return_pct < min_return:
            failures.append(f"{days}d return {return_pct:.2f}% < {min_return:.2f}%")
        if win_rate < min_win_rate:
            failures.append(f"{days}d win rate {win_rate:.2%} < {min_win_rate:.2%}")

    return {
        "complete": not failures,
        "failures": failures,
        "required_windows": list(required_windows),
        "min_win_rate": min_win_rate,
        "min_pnl": min_pnl,
        "min_pnl_by_window": min_pnl_by_window or {},
        "min_return_by_window": min_return_by_window or {},
    }
