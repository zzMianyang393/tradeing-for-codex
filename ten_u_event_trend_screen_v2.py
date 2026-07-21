"""Sealed-screen replay for the persistence-confirmed event-trend v2."""

from __future__ import annotations

import argparse
from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

from ten_u_event_trend_contract_v1 import EventTrendConfig
from ten_u_event_trend_contract_v2 import (
    PersistentEventTrendConfig,
    PersistentEventTrendScreenGate,
    PersistentEventTrendWindows,
    build_preregistration_v2,
)
from ten_u_event_trend_data_v1 import HOUR_MS, parse_utc
from ten_u_event_trend_formation_v1 import (
    EntryProposal,
    FundingPoint,
    HourBar,
    Ignition,
    InstrumentSpec,
    aggregate_four_hour,
    find_ignitions,
    load_bars,
    load_funding,
    simulate_trade,
    wilder_atr,
)


@dataclass(frozen=True)
class PersistenceConfirmation:
    symbol: str
    direction: str
    ignition_ts: int
    confirmation_ts: int
    midpoint: float
    score: float


def _iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def _execution_config(config: PersistentEventTrendConfig) -> EventTrendConfig:
    """Map v2's explicitly frozen execution fields into the tested v1 simulator."""
    return EventTrendConfig(
        symbols=config.symbols,
        pullback_wait_hours=config.post_confirmation_pullback_wait_hours,
        atr_1h_period=config.atr_period_1h,
        disaster_stop_buffer_atr=config.disaster_stop_buffer_atr,
        maximum_disaster_stop_distance=config.maximum_disaster_stop_distance,
        maximum_holding_hours=config.maximum_holding_hours,
        minimum_holding_before_trailing_hours=config.trailing_starts_after_hours,
        initial_equity=config.initial_equity,
        risk_per_trade=config.risk_per_trade,
        maximum_effective_leverage=config.maximum_effective_leverage,
        taker_fee_each_side=config.taker_fee_each_side,
        slippage_each_side=config.slippage_each_side,
        consecutive_loss_cooldown_trades=config.consecutive_loss_cooldown_trades,
        cooldown_hours=config.cooldown_hours,
        daily_loss_halt=config.daily_loss_halt,
        peak_drawdown_halt=config.peak_drawdown_halt,
        ruin_equity=config.ruin_equity,
    )


def find_persistence_confirmations(
    symbol: str,
    bars: list[HourBar],
    config: PersistentEventTrendConfig,
    screen_start_ms: int,
    screen_end_ms: int,
) -> list[PersistenceConfirmation]:
    execution = _execution_config(config)
    four = aggregate_four_hour(bars)
    base = find_ignitions(symbol, four, execution, screen_start_ms, screen_end_ms)
    by_close = {bar.close_ts: index for index, bar in enumerate(four)}
    results: list[PersistenceConfirmation] = []
    for ignition in base:
        index = by_close[ignition.signal_ts]
        if index + config.persistence_completed_4h_bars >= len(four):
            continue
        trigger = four[index]
        following = four[index + 1 : index + 1 + config.persistence_completed_4h_bars]
        if following[-1].close_ts >= screen_end_ms:
            continue
        if ignition.direction == "long":
            holds = all(bar.close >= ignition.midpoint for bar in following)
            breaks = following[-1].close > trigger.high
        else:
            holds = all(bar.close <= ignition.midpoint for bar in following)
            breaks = following[-1].close < trigger.low
        if holds and breaks:
            results.append(
                PersistenceConfirmation(
                    symbol=symbol,
                    direction=ignition.direction,
                    ignition_ts=ignition.signal_ts,
                    confirmation_ts=following[-1].close_ts,
                    midpoint=ignition.midpoint,
                    score=ignition.score,
                )
            )
    return results


def build_v2_proposals(
    symbol: str,
    bars: list[HourBar],
    confirmations: list[PersistenceConfirmation],
    config: PersistentEventTrendConfig,
    screen_end_ms: int,
    *,
    allow_entry_at_end: bool = False,
) -> list[EntryProposal]:
    timestamps = [bar.ts for bar in bars]
    atr = wilder_atr(bars, config.atr_period_1h)
    result: list[EntryProposal] = []
    for confirmation in confirmations:
        start = bisect_left(timestamps, confirmation.confirmation_ts)
        saw_counter = False
        lows: list[float] = []
        highs: list[float] = []
        for index in range(
            start,
            min(start + config.post_confirmation_pullback_wait_hours, len(bars)),
        ):
            bar = bars[index]
            if bar.ts >= screen_end_ms:
                break
            previous = bars[index - 1]
            lows.append(bar.low)
            highs.append(bar.high)
            if confirmation.direction == "long":
                if bar.close < confirmation.midpoint:
                    break
                saw_counter = saw_counter or bar.close < previous.close
                resumed = saw_counter and bar.close > previous.high
                structural = min(lows)
            else:
                if bar.close > confirmation.midpoint:
                    break
                saw_counter = saw_counter or bar.close > previous.close
                resumed = saw_counter and bar.close < previous.low
                structural = max(highs)
            if not resumed or atr[index] is None:
                continue
            # The order is known at this completed bar's close.  A prospective
            # observer must not need the next bar to finish before recording it.
            entry_ts = bar.ts + HOUR_MS
            entry_outside = entry_ts > screen_end_ms or (
                entry_ts == screen_end_ms and not allow_entry_at_end
            )
            if entry_outside:
                break
            result.append(
                EntryProposal(
                    symbol=symbol,
                    direction=confirmation.direction,
                    ignition_ts=confirmation.ignition_ts,
                    entry_ts=entry_ts,
                    structural_invalidation=structural,
                    atr_1h=float(atr[index]),
                    score=confirmation.score,
                )
            )
            break
    return result


def _screen_gate(
    report: dict[str, Any], gate: PersistentEventTrendScreenGate
) -> tuple[str, list[str]]:
    if report["trades"] < gate.minimum_trades:
        return "sealed_screen_insufficient_evidence", ["trades_below_minimum"]
    reasons: list[str] = []
    if report["trades_by_symbol"].get("RAVE-USDT-SWAP", 0) < gate.minimum_rave_trades:
        reasons.append("rave_trades_below_minimum")
    if report["trades_by_symbol"].get("LAB-USDT-SWAP", 0) < gate.minimum_lab_trades:
        reasons.append("lab_trades_below_minimum")
    if report["profit_factor"] < float(gate.minimum_profit_factor):
        reasons.append("profit_factor_below_minimum")
    if report["ending_equity"] < float(gate.minimum_ending_equity):
        reasons.append("ending_equity_below_minimum")
    if report["max_drawdown_fraction"] > float(gate.maximum_drawdown_fraction):
        reasons.append("drawdown_above_maximum")
    if report["peak_profit_retention"] < float(gate.minimum_peak_profit_retention):
        reasons.append("peak_profit_retention_below_minimum")
    if report["stopped_then_recovered_fraction"] > float(
        gate.maximum_stopped_then_recovered_fraction
    ):
        reasons.append("stopped_then_recovered_above_maximum")
    if report["median_winner_capture"] < float(gate.minimum_median_winner_capture):
        reasons.append("winner_capture_below_minimum")
    return ("sealed_screen_pass_prospective_only" if not reasons else "sealed_screen_fail"), reasons


def next_entry_available_at(trade: dict[str, Any]) -> int:
    """Return the first causal entry open after a completed trade.

    A hard stop is only known after the hourly bar has opened and traded through
    the stop.  Re-entering at that same bar's open would use intrabar future
    information.  Other exits execute at a known bar open and may rotate there.
    """
    exit_ts = int(trade["exit_ts"])
    return exit_ts + HOUR_MS if trade["exit_reason"] == "hard_disaster_stop" else exit_ts


def replay_proposals(
    proposals: list[EntryProposal],
    bars_by_symbol: dict[str, list[HourBar]],
    funding_by_symbol: dict[str, list[FundingPoint]],
    specs: dict[str, InstrumentSpec],
    config: PersistentEventTrendConfig,
    end_ms: int,
) -> dict[str, Any]:
    execution = _execution_config(config)
    proposals.sort(key=lambda item: (item.entry_ts, -item.score, item.symbol))
    equity = float(config.initial_equity)
    peak_realized = equity
    peak_marked = equity
    max_drawdown = 0.0
    available_after = 0
    cooldown_until = 0
    consecutive_losses = 0
    daily_date: str | None = None
    daily_start_equity = equity
    daily_halt_date: str | None = None
    permanent_state: str | None = None
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    index = 0
    while index < len(proposals):
        timestamp = proposals[index].entry_ts
        group: list[EntryProposal] = []
        while index < len(proposals) and proposals[index].entry_ts == timestamp:
            group.append(proposals[index])
            index += 1
        if timestamp < available_after:
            skipped.extend({"symbol": item.symbol, "entry_ts": timestamp, "reason": "signal_during_open"} for item in group)
            continue
        date = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()
        if date != daily_date:
            daily_date, daily_start_equity, daily_halt_date = date, equity, None
        state_reason = (
            permanent_state
            or ("cooldown" if timestamp < cooldown_until else None)
            or ("daily_loss_halt" if daily_halt_date == date else None)
        )
        if state_reason:
            skipped.extend({"symbol": item.symbol, "entry_ts": timestamp, "reason": state_reason} for item in group)
            continue
        chosen: EntryProposal | None = None
        trade: dict[str, Any] | None = None
        ranked = sorted(group, key=lambda item: (-item.score, item.symbol))
        for item in ranked:
            candidate = simulate_trade(
                item,
                bars_by_symbol[item.symbol],
                funding_by_symbol[item.symbol],
                specs[item.symbol],
                execution,
                equity,
                end_ms,
            )
            if candidate["accepted"]:
                chosen, trade = item, candidate
                break
            skipped.append({"symbol": item.symbol, "entry_ts": timestamp, **candidate})
        if chosen is None or trade is None:
            continue
        skipped.extend(
            {"symbol": item.symbol, "entry_ts": timestamp, "reason": "same_timestamp_arbitration"}
            for item in ranked[ranked.index(chosen) + 1 :]
        )
        before = equity
        for mark in trade.pop("marks"):
            mark_equity = float(mark["equity"])
            peak_marked = max(peak_marked, mark_equity)
            max_drawdown = max(max_drawdown, (peak_marked - mark_equity) / peak_marked)
        equity = max(0.0, equity + trade["net_pnl"])
        trade["equity_before"], trade["equity_after"] = before, equity
        accepted.append(trade)
        available_after = next_entry_available_at(trade)
        peak_realized = max(peak_realized, equity)
        peak_marked = max(peak_marked, equity)
        max_drawdown = max(max_drawdown, (peak_marked - equity) / peak_marked)
        if trade["net_pnl"] < 0:
            consecutive_losses += 1
            if consecutive_losses >= config.consecutive_loss_cooldown_trades:
                cooldown_until = trade["exit_ts"] + config.cooldown_hours * HOUR_MS
                consecutive_losses = 0
        else:
            consecutive_losses = 0
        exit_date = datetime.fromtimestamp(trade["exit_ts"] / 1000, tz=timezone.utc).date().isoformat()
        if exit_date != daily_date:
            daily_date, daily_start_equity = exit_date, before
        if daily_start_equity and (daily_start_equity - equity) / daily_start_equity >= float(
            config.daily_loss_halt
        ):
            daily_halt_date = exit_date
        realized_drawdown = (peak_realized - equity) / peak_realized
        if equity <= float(config.ruin_equity):
            permanent_state = "ruined"
        elif realized_drawdown >= float(config.peak_drawdown_halt):
            permanent_state = "peak_drawdown_halt"

    positive = [item["net_pnl"] for item in accepted if item["net_pnl"] > 0]
    negative = [-item["net_pnl"] for item in accepted if item["net_pnl"] < 0]
    captures = [item["winner_capture_fraction"] for item in accepted if item["winner_capture_fraction"] is not None]
    hard_stopped = [
        item for item in accepted if item["exit_reason"] == "hard_disaster_stop"
    ]
    structure_exited = [
        item
        for item in accepted
        if item["exit_reason"]
        in {"structural_close_invalidation", "four_hour_structure_trail"}
    ]
    return {
        "starting_equity": float(config.initial_equity),
        "ending_equity": equity,
        "peak_equity": peak_marked,
        "return_fraction": equity / float(config.initial_equity) - 1,
        "max_drawdown_fraction": max_drawdown,
        "trades": len(accepted),
        "wins": len(positive),
        "trades_by_symbol": {symbol: sum(item["symbol"] == symbol for item in accepted) for symbol in config.symbols},
        "profit_factor": sum(positive) / sum(negative) if negative else (1_000_000_000.0 if positive else 0.0),
        "total_fees": sum(item["fees"] for item in accepted),
        "total_slippage": sum(item["slippage_cost"] for item in accepted),
        "total_funding_pnl": sum(item["funding_pnl"] for item in accepted),
        "peak_profit_retention": (
            max(0.0, (equity - float(config.initial_equity)) / (peak_marked - float(config.initial_equity)))
            if peak_marked > float(config.initial_equity)
            else 0.0
        ),
        "hard_stop_count": len(hard_stopped),
        "stopped_then_recovered_fraction": (
            sum(item["hard_stop_recovered_entry"] for item in hard_stopped)
            / len(hard_stopped)
            if hard_stopped
            else 0.0
        ),
        "hard_stop_recovered_1r_fraction": (
            sum(item["hard_stop_recovered_1r"] for item in hard_stopped)
            / len(hard_stopped)
            if hard_stopped
            else 0.0
        ),
        "structure_exit_recovered_entry_fraction": (
            sum(item["structure_exit_recovered_entry"] for item in structure_exited)
            / len(structure_exited)
            if structure_exited
            else 0.0
        ),
        "median_winner_capture": median(captures) if captures else 0.0,
        "permanent_account_state": permanent_state or "active_or_temporary_cooldown",
        "skipped": skipped,
        "trades_detail": accepted,
    }


def run_sealed_screen(
    data_dir: Path,
    preregistration_path: Path,
    manifest_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    if json.loads(preregistration_path.read_text(encoding="utf-8")) != build_preregistration_v2():
        raise ValueError("v2 preregistration drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("coverage_status") != "PASS":
        raise ValueError("dataset coverage failed")
    config = PersistentEventTrendConfig()
    gate = PersistentEventTrendScreenGate()
    windows = PersistentEventTrendWindows()
    start_ms, end_ms = parse_utc(windows.sealed_screen_start), parse_utc(windows.sealed_screen_end)
    bars_by_symbol: dict[str, list[HourBar]] = {}
    funding_by_symbol: dict[str, list[FundingPoint]] = {}
    specs: dict[str, InstrumentSpec] = {}
    funding_coverage: dict[str, Any] = {}
    funding_file_sha256: dict[str, str] = {}
    confirmations_by_symbol: dict[str, int] = {}
    proposals_by_symbol: dict[str, int] = {}
    proposals: list[EntryProposal] = []
    for symbol in config.symbols:
        item = manifest["symbols"][symbol]
        path = Path(item["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"dataset fingerprint drift for {symbol}")
        bars = load_bars(path)
        bars_by_symbol[symbol] = bars
        funding_path = data_dir / f"{symbol}_funding.csv"
        funding_file_sha256[symbol] = hashlib.sha256(funding_path.read_bytes()).hexdigest()
        funding_by_symbol[symbol] = load_funding(funding_path)
        screen_funding = [
            point for point in funding_by_symbol[symbol] if start_ms <= point.ts < end_ms
        ]
        maximum_gap_hours = max(
            (
                (right.ts - left.ts) / HOUR_MS
                for left, right in zip(screen_funding, screen_funding[1:])
            ),
            default=math.inf,
        )
        boundary_covered = bool(
            screen_funding
            and screen_funding[0].ts <= start_ms + 8 * HOUR_MS
            and screen_funding[-1].ts >= end_ms - 8 * HOUR_MS
        )
        funding_coverage[symbol] = {
            "points": len(screen_funding),
            "first": _iso(screen_funding[0].ts) if screen_funding else None,
            "last": _iso(screen_funding[-1].ts) if screen_funding else None,
            "maximum_gap_hours": maximum_gap_hours,
            "boundary_covered": boundary_covered,
            "status": "PASS" if maximum_gap_hours <= 8 and boundary_covered else "FAIL",
        }
        instrument = item["instrument"]
        specs[symbol] = InstrumentSpec(
            symbol,
            float(instrument["ctVal"]),
            float(instrument["lotSz"]),
            float(instrument["minSz"]),
        )
        confirmations = find_persistence_confirmations(symbol, bars, config, start_ms, end_ms)
        symbol_proposals = build_v2_proposals(symbol, bars, confirmations, config, end_ms)
        confirmations_by_symbol[symbol] = len(confirmations)
        proposals_by_symbol[symbol] = len(symbol_proposals)
        proposals.extend(symbol_proposals)
    if any(item["status"] != "PASS" for item in funding_coverage.values()):
        raise ValueError("actual sealed-screen funding coverage is incomplete")
    account = replay_proposals(proposals, bars_by_symbol, funding_by_symbol, specs, config, end_ms)
    status, reasons = _screen_gate(account, gate)
    report = {
        "phase": "sealed_historical_screen",
        "formal_status": status,
        "strategy_id": config.strategy_id,
        "config_fingerprint": config.fingerprint(),
        "screen_gate_fingerprint": gate.fingerprint(),
        "screen_start": windows.sealed_screen_start,
        "screen_end": windows.sealed_screen_end,
        "v1_development_metrics_accessed": False,
        "case_contaminated_metrics_accessed": False,
        "prospective_metrics_accessed": False,
        "funding_cost_status": "actual_history_applied",
        "funding_coverage": funding_coverage,
        "funding_file_sha256": funding_file_sha256,
        "confirmations_by_symbol": confirmations_by_symbol,
        "entry_proposals_by_symbol": proposals_by_symbol,
        "gate_reasons": reasons,
        "account": account,
        "interpretation": (
            "prospective_candidate_only_not_validated"
            if status == "sealed_screen_pass_prospective_only"
            else "prospective_observation_only_no_edge_claim"
            if status == "sealed_screen_insufficient_evidence"
            else "reject_v2"
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/event_trend_v1"))
    parser.add_argument("--preregistration", type=Path, default=Path("reports/ten_u_event_trend_preregistration_v2.json"))
    parser.add_argument("--manifest", type=Path, default=Path("data/event_trend_v1/hourly_dataset_manifest_v1.json"))
    parser.add_argument("--report", type=Path, default=Path("reports/ten_u_event_trend_screen_v2.json"))
    args = parser.parse_args()
    report = run_sealed_screen(args.data, args.preregistration, args.manifest, args.report)
    print(json.dumps({key: value for key, value in report.items() if key != "account"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
