from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

from state_db import StateDB


# ---------------------------------------------------------------------------
# Report commands
# ---------------------------------------------------------------------------

def cmd_daily(args: argparse.Namespace) -> None:
    """Show today's trading summary."""
    db = _get_db(args)
    try:
        recent = db.get_recent_trades(100)
        # Filter to today's trades (simplified - by most recent)
        print(f"=== Daily Trading Summary ===")
        print(f"Total Recent Trades: {len(recent)}")

        if not recent:
            print("No trades found")
            return

        total_pnl = sum(t.get("pnl", 0) or 0 for t in recent)
        wins = sum(1 for t in recent if (t.get("pnl", 0) or 0) > 0)
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
        recent = db.get_recent_trades(500)
        print(f"=== Weekly Trading Summary ===")
        print(f"Total Trades: {len(recent)}")

        if not recent:
            print("No trades found")
            return

        total_pnl = sum(t.get("pnl", 0) or 0 for t in recent)
        wins = sum(1 for t in recent if (t.get("pnl", 0) or 0) > 0)
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
    # This would integrate with the existing rolling_window_audit.py
    print("=== Rolling Audit ===")
    print("To run audit, use: python rolling_window_audit.py")


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Trading Report CLI")
    parser.add_argument("--db-path", required=True, help="SQLite database path")

    subparsers = parser.add_subparsers(dest="command", help="Report command")

    subparsers.add_parser("daily", help="Daily trading summary")
    subparsers.add_parser("weekly", help="Weekly trading summary")
    subparsers.add_parser("performance", help="Performance breakdown")
    subparsers.add_parser("risk", help="Risk status")
    subparsers.add_parser("positions", help="Current positions")
    subparsers.add_parser("equity-curve", help="Equity curve")
    subparsers.add_parser("audit", help="Run rolling audit")

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
