from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from pathlib import Path

from config import BacktestConfig
from rolling_window_audit import print_report, run_rolling_audit
from state_db import StateDB


# ---------------------------------------------------------------------------
# Report commands
# ---------------------------------------------------------------------------

def cmd_daily(args: argparse.Namespace) -> None:
    """Show today's trading summary."""
    db = _get_db(args)
    try:
        target = _target_date(args)
        start = datetime.combine(target, time.min)
        end = datetime.combine(target + timedelta(days=1), time.min)
        recent = _filter_trades_by_time(db.get_recent_trades(_trade_limit(args)), start, end)
        payload = _trade_summary(recent, group_by="symbol")
        payload.update({"period": "daily", "date": target.isoformat()})
        if getattr(args, "json", False):
            _print_json(payload)
            return

        print(f"=== Daily Trading Summary ===")
        print(f"Total Recent Trades: {len(recent)}")

        if not recent:
            print("No trades found")
            return

        total_pnl = payload["total_pnl"]
        wins = payload["wins"]
        print(f"Total PnL:           {total_pnl:.4f}")
        print(f"Win Rate:            {wins/len(recent):.2%}")

        # By symbol
        by_symbol = defaultdict(list)
        for t in recent:
            by_symbol[t["symbol"]].append(t)

        print(f"\n--- By Symbol ---")
        for symbol, trades in sorted(by_symbol.items()):
            pnl = sum(t.get("pnl", 0) or 0 for t in trades)
            print(f"  {symbol}: {len(trades)} trades, PnL={pnl:.4f}")
    finally:
        db.close()


def cmd_weekly(args: argparse.Namespace) -> None:
    """Show weekly trading summary."""
    db = _get_db(args)
    try:
        target = _target_date(args)
        start_date = target - timedelta(days=target.weekday())
        end_date = start_date + timedelta(days=7)
        start = datetime.combine(start_date, time.min)
        end = datetime.combine(end_date, time.min)
        recent = _filter_trades_by_time(db.get_recent_trades(_trade_limit(args)), start, end)
        payload = _trade_summary(recent, group_by="signal_reason")
        payload.update({"period": "weekly", "week_start": start_date.isoformat(), "week_end": end_date.isoformat()})
        if getattr(args, "json", False):
            _print_json(payload)
            return

        print(f"=== Weekly Trading Summary ===")
        print(f"Total Trades: {len(recent)}")

        if not recent:
            print("No trades found")
            return

        total_pnl = payload["total_pnl"]
        wins = payload["wins"]
        print(f"Total PnL:           {total_pnl:.4f}")
        print(f"Win Rate:            {wins/len(recent):.2%}")

        # By reason
        by_reason = defaultdict(list)
        for t in recent:
            by_reason[t.get("signal_reason", "unknown")].append(t)

        print(f"\n--- By Signal Reason ---")
        for reason, trades in sorted(by_reason.items()):
            pnl = sum(t.get("pnl", 0) or 0 for t in trades)
            print(f"  {reason}: {len(trades)} trades, PnL={pnl:.4f}")
    finally:
        db.close()


def cmd_performance(args: argparse.Namespace) -> None:
    """Show performance breakdown by strategy/symbol/regime."""
    db = _get_db(args)
    try:
        summary = db.trade_summary()
        print(f"=== Performance Breakdown ===")
        print(f"Total Trades:     {summary.get('total', 0)}")
        print(f"Wins:             {summary.get('wins', 0)}")
        print(f"Win Rate:         {summary.get('win_rate', 0):.2%}")
        print(f"Total PnL:        {summary.get('total_pnl', 0):.4f}")
        print(f"Avg PnL:          {summary.get('avg_pnl', 0):.4f}")
        print(f"Best Trade:       {summary.get('best_trade', 0):.4f}")
        print(f"Worst Trade:      {summary.get('worst_trade', 0):.4f}")

        # By symbol
        recent = db.get_recent_trades(1000)
        by_symbol = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wins": 0})
        for t in recent:
            sym = t["symbol"]
            by_symbol[sym]["count"] += 1
            pnl = t.get("pnl", 0) or 0
            by_symbol[sym]["pnl"] += pnl
            if pnl > 0:
                by_symbol[sym]["wins"] += 1

        print(f"\n--- By Symbol ---")
        for sym, data in sorted(by_symbol.items(), key=lambda x: -x[1]["pnl"]):
            wr = data["wins"] / data["count"] if data["count"] > 0 else 0
            print(f"  {sym}: {data['count']} trades, PnL={data['pnl']:.4f}, WR={wr:.2%}")
    finally:
        db.close()


def cmd_risk(args: argparse.Namespace) -> None:
    """Show risk status."""
    db = _get_db(args)
    try:
        events = db.get_risk_events(50)
        print(f"=== Risk Events ===")
        print(f"Total Events: {len(events)}")

        if not events:
            print("No risk events recorded")
            return

        # Group by type
        by_type = defaultdict(list)
        for e in events:
            by_type[e["event_type"]].append(e)

        for event_type, evts in sorted(by_type.items()):
            print(f"\n--- {event_type} ({len(evts)}) ---")
            for e in evts[:5]:  # Show last 5
                print(f"  [{e['ts']}] {e.get('detail', '')}")
    finally:
        db.close()


def cmd_positions(args: argparse.Namespace) -> None:
    """Show current positions."""
    db = _get_db(args)
    try:
        positions = db.get_open_positions()
        print(f"=== Open Positions ===")
        print(f"Count: {len(positions)}")

        if not positions:
            print("No open positions")
            return

        for p in positions:
            print(f"  {p['symbol']} {p['direction']} qty={p.get('qty', 0)} "
                  f"entry={p.get('entry_price', 0):.2f} pnl={p.get('unrealized_pnl', 0):.4f}")
    finally:
        db.close()


def cmd_equity_curve(args: argparse.Namespace) -> None:
    """Show equity curve (ASCII chart)."""
    db = _get_db(args)
    try:
        history = db.get_account_history()
        print(f"=== Equity Curve ===")

        if not history:
            print("No account history found")
            return

        # Simple ASCII chart
        equities = [h["equity"] for h in history]
        min_eq = min(equities)
        max_eq = max(equities)
        width = 50

        print(f"Range: {min_eq:.2f} - {max_eq:.2f}")
        print()

        for i, eq in enumerate(equities[-20:]):  # Show last 20
            normalized = (eq - min_eq) / (max_eq - min_eq) if max_eq > min_eq else 0.5
            bar_len = int(normalized * width)
            bar = "█" * bar_len
            print(f"  {eq:8.2f} |{bar}")
    finally:
        db.close()


def cmd_audit(args: argparse.Namespace) -> None:
    """Run rolling audit on backtest results."""
    config = BacktestConfig()
    module = getattr(args, "module", "default")
    if module == "funding":
        config = replace(config, enable_funding_module=True)
    elif module == "open-interest":
        config = replace(config, enable_open_interest_module=True)
    elif module == "trade-flow":
        config = replace(config, enable_trade_flow_module=True)
    elif module == "order-book":
        config = replace(
            config,
            rm_max_order_book_spread_pct=0.002,
            rm_min_order_book_depth_quote=100_000.0,
        )

    report = run_rolling_audit(
        getattr(args, "data", Path("data")),
        config,
        stride_days=getattr(args, "stride_days", 14),
        max_windows=getattr(args, "max_windows", 12),
        warmup_days=getattr(args, "warmup_days", 45),
    )
    report["module"] = module
    out_path = getattr(args, "out", Path("reports") / "rolling_window_audit.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if getattr(args, "json", False):
        _print_json(report)
        return
    print_report(report)
    print(f"report={out_path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_db(args: argparse.Namespace) -> StateDB:
    """Get StateDB from args."""
    db_path = getattr(args, "db_path", None)
    if not db_path:
        print("Error: --db-path required")
        sys.exit(1)
    return StateDB(Path(db_path))


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _target_date(args: argparse.Namespace) -> date:
    value = getattr(args, "date", None)
    if value:
        return date.fromisoformat(value)
    return datetime.now().date()


def _trade_limit(args: argparse.Namespace) -> int:
    return int(getattr(args, "limit", 100000))


def _filter_trades_by_time(trades: list[dict], start: datetime, end: datetime) -> list[dict]:
    return [
        trade
        for trade in trades
        if (trade_time := _trade_time(trade)) is not None and start <= trade_time < end
    ]


def _trade_time(trade: dict) -> datetime | None:
    value = trade.get("exit_time") or trade.get("entry_time")
    if not value:
        return None
    text = str(value).replace("T", " ")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _trade_summary(trades: list[dict], group_by: str) -> dict:
    grouped = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wins": 0})
    total_pnl = 0.0
    wins = 0
    for trade in trades:
        pnl = float(trade.get("pnl") or 0.0)
        total_pnl += pnl
        if pnl > 0:
            wins += 1
        key = trade.get(group_by) or "unknown"
        grouped[key]["count"] += 1
        grouped[key]["pnl"] += pnl
        if pnl > 0:
            grouped[key]["wins"] += 1

    group_name = "by_symbol" if group_by == "symbol" else "by_reason"
    return {
        "total_trades": len(trades),
        "wins": wins,
        "win_rate": round(wins / len(trades), 4) if trades else 0.0,
        "total_pnl": round(total_pnl, 4),
        group_name: {
            key: {
                "count": int(value["count"]),
                "pnl": round(float(value["pnl"]), 4),
                "wins": int(value["wins"]),
            }
            for key, value in sorted(grouped.items())
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Trading Report CLI")
    parser.add_argument("--db-path", required=True, help="SQLite database path")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--limit", type=int, default=100000, help="Maximum recent trades to scan")

    subparsers = parser.add_subparsers(dest="command", help="Report command")

    daily_parser = subparsers.add_parser("daily", help="Daily trading summary")
    daily_parser.add_argument("--date", help="Report date in YYYY-MM-DD format")
    weekly_parser = subparsers.add_parser("weekly", help="Weekly trading summary")
    weekly_parser.add_argument("--date", help="Any date in the target ISO week, YYYY-MM-DD")
    subparsers.add_parser("performance", help="Performance breakdown")
    subparsers.add_parser("risk", help="Risk status")
    subparsers.add_parser("positions", help="Current positions")
    subparsers.add_parser("equity-curve", help="Equity curve")
    audit_parser = subparsers.add_parser("audit", help="Run rolling audit")
    audit_parser.add_argument("--data", type=Path, default=Path("data"))
    audit_parser.add_argument("--out", type=Path, default=Path("reports") / "rolling_window_audit.json")
    audit_parser.add_argument(
        "--module",
        choices=("default", "funding", "open-interest", "trade-flow", "order-book"),
        default="default",
    )
    audit_parser.add_argument("--stride-days", type=int, default=14)
    audit_parser.add_argument("--max-windows", type=int, default=12)
    audit_parser.add_argument("--warmup-days", type=int, default=45)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "daily": cmd_daily,
        "weekly": cmd_weekly,
        "performance": cmd_performance,
        "risk": cmd_risk,
        "positions": cmd_positions,
        "equity-curve": cmd_equity_curve,
        "audit": cmd_audit,
    }
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
