"""Capital-constrained daily equity simulation for downtrend RSI rebounds.

The simulator consumes frozen research events, enforces fixed cash and position
limits, and marks accepted positions to market on daily closes. It remains a
research diagnostic and has no connection to trading execution.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from daily_rsi_mean_revert_audit import DAY_MS, PriceBar, load_daily_for_base
from downtrend_rebound_event_time_filter_audit import HYPOTHESES, load_json, select_hypotheses


INITIAL_CAPITAL = 100_000.0
MAX_POSITIONS = 5
POSITION_FRACTION = 0.20
ENTRY_COST_RATE = 0.0008
EXIT_COST_RATE = 0.0008


def load_price_maps(data_dir: Path, events: list[dict[str, Any]]) -> dict[str, dict[int, PriceBar]]:
    maps: dict[str, dict[int, PriceBar]] = {}
    for symbol in sorted({str(event.get("symbol") or "") for event in events if event.get("symbol")}):
        base = symbol.split("-", 1)[0]
        daily, _source = load_daily_for_base(data_dir, base)
        maps[symbol] = {bar.ts: bar for bar in daily}
    return maps


def candidate_priority(event: dict[str, Any], mode: str = "signal_rsi_then_symbol") -> tuple[float, str]:
    if mode == "symbol":
        return (0.0, str(event.get("symbol") or ""))
    if mode == "event_score_then_symbol":
        return (float(event.get("portfolio_priority") or 100.0), str(event.get("symbol") or ""))
    return (float(event.get("signal_rsi") or 100.0), str(event.get("symbol") or ""))


def price_at(
    price_maps: dict[str, dict[int, PriceBar]],
    symbol: str,
    ts: int,
    field: str,
    fallback: float,
) -> float:
    bar = price_maps.get(symbol, {}).get(ts)
    return float(getattr(bar, field)) if bar is not None else fallback


def marked_position_value(position: dict[str, Any], mark_price: float, include_exit_cost: bool = False) -> float:
    if mark_price <= 0:
        return 0.0
    direction = str(position.get("direction") or "long")
    if direction == "short":
        value = (
            float(position["cash_outlay"])
            * (1.0 - ENTRY_COST_RATE)
            * float(position["entry_price"])
            / mark_price
        )
    else:
        value = float(position["quantity"]) * mark_price
    return value * (1.0 - EXIT_COST_RATE) if include_exit_cost else value


def maximum_drawdown(equity_curve: list[dict[str, Any]], initial_equity: float | None = None) -> float:
    peak = float(initial_equity) if initial_equity is not None else 0.0
    worst = 0.0
    for point in equity_curve:
        equity = float(point["equity"])
        peak = max(peak, equity)
        if peak > 0:
            worst = max(worst, (peak - equity) / peak)
    return round(worst, 6)


def positive_month_concentration(closed_positions: list[dict[str, Any]]) -> float:
    positive_by_month: dict[str, float] = defaultdict(float)
    for position in closed_positions:
        pnl = float(position["realized_pnl"])
        if pnl > 0:
            positive_by_month[str(position["exit_timestamp_utc"])[:7]] += pnl
    total = sum(positive_by_month.values())
    top = max(positive_by_month.values()) if positive_by_month else 0.0
    return round(top / total, 6) if total else 0.0


def simulate_portfolio(
    events: list[dict[str, Any]],
    price_maps: dict[str, dict[int, PriceBar]],
    initial_capital: float = INITIAL_CAPITAL,
    max_positions: int = MAX_POSITIONS,
    position_fraction: float = POSITION_FRACTION,
    priority_mode: str = "signal_rsi_then_symbol",
    one_position_per_symbol: bool = True,
    component_position_caps: dict[str, int] | None = None,
) -> dict[str, Any]:
    valid_events = [
        event
        for event in events
        if int(event.get("entry_ts") or 0) > 0
        and int(event.get("exit_ts") or 0) > int(event.get("entry_ts") or 0)
        and float(event.get("entry_price") or 0.0) > 0
        and float(event.get("exit_price") or 0.0) > 0
    ]
    if not valid_events:
        return {
            "candidate_events": 0,
            "accepted_positions": 0,
            "capacity_rejected_events": 0,
            "initial_equity": round(initial_capital, 6),
            "final_equity": round(initial_capital, 6),
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "realized_win_rate": 0.0,
            "max_concurrent_positions": 0,
            "average_gross_exposure": 0.0,
            "peak_gross_exposure": 0.0,
            "capital_turnover": 0.0,
            "top_positive_month_share": 0.0,
            "equity_curve": [],
            "closed_positions": [],
            "rejected_events": [],
        }

    entries: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in valid_events:
        entries[int(event["entry_ts"])].append(event)

    first_day = min(int(event["entry_ts"]) for event in valid_events) // DAY_MS * DAY_MS
    last_day = max(int(event["exit_ts"]) for event in valid_events) // DAY_MS * DAY_MS
    action_times_by_day: dict[int, set[int]] = defaultdict(set)
    for event in valid_events:
        entry_ts = int(event["entry_ts"])
        exit_ts = int(event["exit_ts"])
        action_times_by_day[entry_ts // DAY_MS * DAY_MS].add(entry_ts)
        action_times_by_day[exit_ts // DAY_MS * DAY_MS].add(exit_ts)
    cash = float(initial_capital)
    active: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    total_allocated = 0.0
    max_concurrent = 0

    for day_ts in range(first_day, last_day + DAY_MS, DAY_MS):
        for action_ts in sorted(action_times_by_day.get(day_ts, set())):
            survivors: list[dict[str, Any]] = []
            for position in active:
                if int(position["exit_ts"]) <= action_ts:
                    exit_price = float(position["exit_price"])
                    proceeds = marked_position_value(position, exit_price, include_exit_cost=True)
                    cash += proceeds
                    realized_pnl = proceeds - float(position["cash_outlay"])
                    closed.append(
                        {
                            **position,
                            "exit_timestamp_utc": str(position.get("exit_timestamp_utc") or ""),
                            "proceeds": round(proceeds, 6),
                            "realized_pnl": round(realized_pnl, 6),
                            "realized_return_pct": round(realized_pnl / float(position["cash_outlay"]) * 100.0, 6),
                        }
                    )
                else:
                    survivors.append(position)
            active = survivors

            open_value = cash
            for position in active:
                symbol = str(position["symbol"])
                entered_today = int(position["entry_ts"]) // DAY_MS * DAY_MS == day_ts
                mark = float(position["last_mark_price"]) if entered_today else price_at(
                    price_maps, symbol, day_ts, "open", float(position["last_mark_price"])
                )
                position["last_mark_price"] = mark
                open_value += marked_position_value(position, mark)

            candidates = sorted(entries.get(action_ts, []), key=lambda event: candidate_priority(event, priority_mode))
            for event in candidates:
                symbol = str(event.get("symbol") or "")
                if one_position_per_symbol and any(str(position["symbol"]) == symbol for position in active):
                    rejected.append({**event, "rejection_reason": "duplicate_symbol_exposure"})
                    continue
                component = str(event.get("component_id") or "")
                component_cap = (component_position_caps or {}).get(component)
                if component_cap is not None:
                    active_component = sum(str(position.get("component_id") or "") == component for position in active)
                    if active_component >= component_cap:
                        rejected.append({**event, "rejection_reason": "component_position_capacity"})
                        continue
                if len(active) >= max_positions:
                    rejected.append({**event, "rejection_reason": "position_capacity"})
                    continue
                target_outlay = open_value * position_fraction
                cash_outlay = min(target_outlay, cash)
                if cash_outlay <= 0:
                    rejected.append({**event, "rejection_reason": "insufficient_cash"})
                    continue
                entry_price = float(event["entry_price"])
                direction = str(event.get("direction") or "long")
                quantity = cash_outlay * (1.0 - ENTRY_COST_RATE) / entry_price if direction == "long" else 0.0
                cash -= cash_outlay
                total_allocated += cash_outlay
                active.append(
                    {
                        "symbol": str(event.get("symbol") or ""),
                        "component_id": str(event.get("component_id") or ""),
                        "direction": direction,
                        "split": str(event.get("split") or ""),
                        "entry_ts": int(event["entry_ts"]),
                        "entry_timestamp_utc": str(event.get("entry_timestamp_utc") or ""),
                        "exit_ts": int(event["exit_ts"]),
                        "exit_timestamp_utc": str(event.get("exit_timestamp_utc") or ""),
                        "entry_price": entry_price,
                        "exit_price": float(event["exit_price"]),
                        "signal_rsi": float(event.get("signal_rsi") or 0.0),
                        "cash_outlay": cash_outlay,
                        "quantity": quantity,
                        "last_mark_price": entry_price,
                    }
                )
        market_value = 0.0
        long_market_value = 0.0
        short_market_value = 0.0
        component_market_values: dict[str, float] = defaultdict(float)
        active_long_positions = 0
        active_short_positions = 0
        for position in active:
            symbol = str(position["symbol"])
            mark = price_at(price_maps, symbol, day_ts, "close", float(position["last_mark_price"]))
            position["last_mark_price"] = mark
            value = marked_position_value(position, mark)
            market_value += value
            direction = str(position.get("direction") or "long")
            if direction == "short":
                short_market_value += value
                active_short_positions += 1
            else:
                long_market_value += value
                active_long_positions += 1
            component_market_values[str(position.get("component_id") or "unassigned")] += value
        equity = cash + market_value
        gross_exposure = market_value / equity if equity > 0 else 0.0
        net_directional_exposure = (long_market_value - short_market_value) / equity if equity > 0 else 0.0
        max_concurrent = max(max_concurrent, len(active))
        equity_curve.append(
            {
                "ts": day_ts,
                "equity": round(equity, 6),
                "cash": round(cash, 6),
                "active_positions": len(active),
                "active_long_positions": active_long_positions,
                "active_short_positions": active_short_positions,
                "gross_exposure": round(gross_exposure, 6),
                "long_exposure": round(long_market_value / equity, 6) if equity > 0 else 0.0,
                "short_exposure": round(short_market_value / equity, 6) if equity > 0 else 0.0,
                "net_directional_exposure": round(net_directional_exposure, 6),
                "component_exposure": {
                    component: round(value / equity, 6) if equity > 0 else 0.0
                    for component, value in sorted(component_market_values.items())
                },
            }
        )

    final_equity = float(equity_curve[-1]["equity"])
    wins = sum(float(position["realized_pnl"]) > 0 for position in closed)
    exposures = [float(point["gross_exposure"]) for point in equity_curve]
    return {
        "candidate_events": len(valid_events),
        "accepted_positions": len(closed),
        "capacity_rejected_events": len(rejected),
        "initial_equity": round(initial_capital, 6),
        "final_equity": round(final_equity, 6),
        "total_return_pct": round((final_equity / initial_capital - 1.0) * 100.0, 6),
        "max_drawdown_pct": round(maximum_drawdown(equity_curve, initial_capital) * 100.0, 6),
        "realized_win_rate": round(wins / len(closed), 6) if closed else 0.0,
        "max_concurrent_positions": max_concurrent,
        "average_gross_exposure": round(mean(exposures), 6) if exposures else 0.0,
        "peak_gross_exposure": round(max(exposures), 6) if exposures else 0.0,
        "capital_turnover": round(total_allocated / initial_capital, 6),
        "top_positive_month_share": positive_month_concentration(closed),
        "equity_curve": equity_curve,
        "closed_positions": closed,
        "rejected_events": rejected,
    }


def simulation_screen(result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if float(result["total_return_pct"]) <= 0:
        reasons.append("total return <= 0")
    if float(result["max_drawdown_pct"]) > 20.0:
        reasons.append(f"maximum drawdown {result['max_drawdown_pct']:.2f}% > 20%")
    if int(result["accepted_positions"]) < 20:
        reasons.append(f"accepted positions {result['accepted_positions']} < 20")
    if float(result["top_positive_month_share"]) > 0.25:
        reasons.append(f"positive-month concentration {result['top_positive_month_share']:.2%} > 25%")
    return reasons


def build_report(event_time_report: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    events = list(event_time_report.get("events", []))
    price_maps = load_price_maps(data_dir, events)
    hypotheses = select_hypotheses(events)
    reviews: dict[str, Any] = {}
    for name in HYPOTHESES:
        split_results: dict[str, Any] = {}
        for split in ("formation", "oos"):
            result = simulate_portfolio(
                [event for event in hypotheses[name] if event.get("split") == split],
                price_maps,
            )
            split_results[split] = {
                **result,
                "screen_reasons": simulation_screen(result),
                "passes_diagnostic_screen": not simulation_screen(result),
            }
        reviews[name] = split_results
    return {
        "report_type": "downtrend_rebound_capital_constrained_simulation",
        "report_date": "2026-07-13",
        "research_id": "downtrend_rebound_capital_constrained_v1",
        "scope": "read_only_daily_mark_to_market_portfolio_diagnostic",
        "portfolio_rules": {
            "initial_capital": INITIAL_CAPITAL,
            "max_positions": MAX_POSITIONS,
            "position_fraction": POSITION_FRACTION,
            "entry_cost_rate": ENTRY_COST_RATE,
            "exit_cost_rate": EXIT_COST_RATE,
            "leverage": 1.0,
            "same_entry_priority": "lower signal_rsi, then symbol ascending",
            "rebalance": False,
        },
        "hypothesis_reviews": reviews,
        "limitations": [
            "This is a deterministic research simulator, not an execution engine.",
            "Daily close marking does not model intraday drawdown or gap slippage beyond the frozen cost floor.",
            "The post-hoc regime interpretation still requires future-window validation.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Downtrend Rebound Capital-Constrained Simulation",
        "",
        "Date: 2026-07-13",
        "",
        "Fixed rules: 100,000 USDT initial capital per split, no leverage, five positions maximum, 20% target allocation per position, and 0.08% cost on each side.",
        "",
        "## Results",
        "",
        "| Hypothesis | Split | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Screen |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name in HYPOTHESES:
        for split in ("formation", "oos"):
            item = report["hypothesis_reviews"][name][split]
            lines.append(
                f"| `{name}` | {split} | {item['candidate_events']} | {item['accepted_positions']} | "
                f"{item['capacity_rejected_events']} | {item['total_return_pct']:+.6f}% | "
                f"{item['max_drawdown_pct']:.6f}% | {item['realized_win_rate']:.2%} | "
                f"{item['average_gross_exposure']:.2%} | {item['peak_gross_exposure']:.2%} | "
                f"{'pass' if item['passes_diagnostic_screen'] else 'blocked'} |"
            )
    lines.extend(["", "## OOS Screen Details", ""])
    for name in HYPOTHESES:
        item = report["hypothesis_reviews"][name]["oos"]
        lines.append(f"### {name}")
        lines.append("")
        if item["screen_reasons"]:
            lines.extend(f"- {reason}" for reason in item["screen_reasons"])
        else:
            lines.append("- Current diagnostic thresholds pass; future-window validation is still mandatory.")
        lines.append("")
    lines.extend(
        [
            "## Safety",
            "",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run capital-constrained downtrend rebound research simulation.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("reports/downtrend_rebound_event_time_filter_audit.json"),
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/downtrend_rebound_capital_constrained_simulation.json"),
    )
    parser.add_argument(
        "--doc",
        type=Path,
        default=Path("docs/downtrend_rebound_capital_constrained_simulation_2026-07-13.md"),
    )
    args = parser.parse_args(argv)
    source = load_json(args.source)
    if not source:
        print(f"ERROR: Cannot load source report {args.source}")
        return 1
    report = build_report(source, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    for name in HYPOTHESES:
        item = report["hypothesis_reviews"][name]["oos"]
        print(
            f"{name}: accepted={item['accepted_positions']}, return={item['total_return_pct']:+.6f}%, "
            f"max_dd={item['max_drawdown_pct']:.6f}%, win={item['realized_win_rate']:.2%}, "
            f"passes={item['passes_diagnostic_screen']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
