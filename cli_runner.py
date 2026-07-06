from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from config import BacktestConfig
from exchange import OKXExchange
from executor import Executor
from risk_manager import RiskManager
from runner import TradingRunner, create_runner
from state_db import StateDB

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> None:
    """Show current trading status."""
    runner = _create_runner(args)
    account = runner.exchange.get_account_balance()
    positions = runner.exchange.get_positions()

    print(f"=== Account Status ===")
    print(f"Equity:           {account.total_equity:.2f} {account.currency}")
    print(f"Available:        {account.available_balance:.2f}")
    print(f"Used Margin:      {account.used_margin:.2f}")
    print(f"Unrealized PnL:   {account.unrealized_pnl:.2f}")
    print()

    if positions:
        print(f"=== Open Positions ({len(positions)}) ===")
        for pos in positions:
            print(f"  {pos.symbol}: {pos.direction} qty={pos.qty} "
                  f"entry={pos.entry_price:.2f} current={pos.current_price:.2f} "
                  f"pnl={pos.unrealized_pnl:.2f}")
    else:
        print("No open positions")

    if runner.executor.risk_manager:
        status = runner.executor.risk_manager.get_status()
        print()
        print(f"=== Risk Status ===")
        print(f"Paused:           {status.is_paused}")
        if status.is_paused:
            print(f"Pause Reason:     {status.pause_reason}")
            print(f"Pause Until:      step {status.pause_until_step}")
        print(f"Daily PnL:        {status.daily_pnl:.4f}")
        print(f"Weekly PnL:       {status.weekly_pnl:.4f}")
        print(f"Consecutive Loss: {status.consecutive_losses}")


def cmd_once(args: argparse.Namespace) -> None:
    """Run one iteration."""
    runner = _create_runner(args)
    report = runner.run_once()
    print(f"=== Run Report ===")
    print(f"Equity:           {report.equity:.2f}")
    print(f"Open Positions:   {report.open_positions}")
    print(f"Signals:          {report.signals_generated}")
    print(f"Orders Placed:    {report.orders_placed}")
    print(f"Orders Rejected:  {report.orders_rejected}")
    if report.errors:
        print(f"Errors:           {report.errors}")


def cmd_loop(args: argparse.Namespace) -> None:
    """Run continuously."""
    runner = _create_runner(args)
    print(f"Starting continuous trading loop (interval={args.interval}s)")
    print("Press Ctrl+C to stop")
    runner.run_loop(interval_seconds=args.interval)


def cmd_dry_run(args: argparse.Namespace) -> None:
    """Run in dry-run mode (no actual orders)."""
    args.dry_run = True
    runner = _create_runner(args)
    print("=== DRY RUN MODE ===")
    print("No actual orders will be placed")
    print()

    if args.once:
        report = runner.run_once()
        print(f"Would have placed {report.orders_placed} orders")
        print(f"Would have rejected {report.orders_rejected} orders")
    else:
        print("Starting dry-run loop (Ctrl+C to stop)")
        runner.run_loop(interval_seconds=args.interval)


def cmd_reconcile(args: argparse.Namespace) -> None:
    """Reconcile positions with exchange."""
    runner = _create_runner(args)
    result = runner.executor.sync_state()
    print(f"=== Reconciliation ===")
    print(f"Consistent:       {result.consistent}")
    print(f"Local Only:       {result.local_only_count}")
    print(f"Exchange Only:    {result.exchange_only_count}")
    if result.details:
        print(f"Details:          {result.details}")


def cmd_report(args: argparse.Namespace) -> None:
    """Generate trading report from state DB."""
    if not args.db_path:
        print("Error: --db-path required for report command")
        sys.exit(1)

    db = StateDB(Path(args.db_path))
    try:
        summary = db.trade_summary()
        recent = db.get_recent_trades(20)
        risk_events = db.get_risk_events(20)

        print("=== Trade Summary ===")
        print(f"Total Trades:     {summary.get('total', 0)}")
        print(f"Wins:             {summary.get('wins', 0)}")
        print(f"Win Rate:         {summary.get('win_rate', 0):.2%}")
        print(f"Total PnL:        {summary.get('total_pnl', 0):.4f}")
        print(f"Avg PnL:          {summary.get('avg_pnl', 0):.4f}")
        print(f"Best Trade:       {summary.get('best_trade', 0):.4f}")
        print(f"Worst Trade:      {summary.get('worst_trade', 0):.4f}")

        if recent:
            print()
            print(f"=== Recent Trades (last {len(recent)}) ===")
            for t in recent:
                print(f"  {t['symbol']} {t['direction']} pnl={t.get('pnl', 0):.4f} "
                      f"reason={t.get('signal_reason', '')} exit={t.get('exit_reason', '')}")

        if risk_events:
            print()
            print(f"=== Risk Events (last {len(risk_events)}) ===")
            for e in risk_events:
                print(f"  [{e['event_type']}] {e.get('detail', '')}")

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_runner(args: argparse.Namespace) -> TradingRunner:
    """Create a runner from CLI args."""
    # Load config
    config = BacktestConfig()

    # Override with env/args if provided
    api_key = getattr(args, "api_key", "") or ""
    secret = getattr(args, "secret", "") or ""
    passphrase = getattr(args, "passphrase", "") or ""
    sandbox = not getattr(args, "live", False)
    dry_run = getattr(args, "dry_run", False)
    symbols = getattr(args, "symbols", None)
    db_path = getattr(args, "db_path", None)

    return create_runner(
        config=config,
        api_key=api_key,
        secret=secret,
        passphrase=passphrase,
        sandbox=sandbox,
        dry_run=dry_run,
        symbols=symbols.split(",") if symbols else None,
        db_path=db_path,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Trading Runner CLI")
    parser.add_argument("--api-key", help="OKX API key (or OKX_API_KEY env)")
    parser.add_argument("--secret", help="OKX secret (or OKX_SECRET env)")
    parser.add_argument("--passphrase", help="OKX passphrase (or OKX_PASSPHRASE env)")
    parser.add_argument("--live", action="store_true", help="Use live trading (default: sandbox)")
    parser.add_argument("--symbols", help="Comma-separated symbol list")
    parser.add_argument("--db-path", help="SQLite database path")
    parser.add_argument("--interval", type=int, default=900, help="Loop interval in seconds")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # status
    subparsers.add_parser("status", help="Show current status")

    # once
    subparsers.add_parser("once", help="Run one iteration")

    # loop
    subparsers.add_parser("loop", help="Run continuously")

    # dry-run
    dry_run_parser = subparsers.add_parser("dry-run", help="Dry run mode")
    dry_run_parser.add_argument("--once", action="store_true", help="Run once only")

    # reconcile
    subparsers.add_parser("reconcile", help="Reconcile positions")

    # report
    subparsers.add_parser("report", help="Generate trading report")

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch
    commands = {
        "status": cmd_status,
        "once": cmd_once,
        "loop": cmd_loop,
        "dry-run": cmd_dry_run,
        "reconcile": cmd_reconcile,
        "report": cmd_report,
    }
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
