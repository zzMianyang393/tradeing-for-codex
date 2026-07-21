"""Formation-only causal replay for the frozen 10U event-trend contract."""

from __future__ import annotations

import argparse
from bisect import bisect_left
import csv
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from ten_u_event_trend_contract_v1 import (
    EventTrendConfig,
    EventTrendFormationGate,
    EventTrendResearchWindows,
    build_preregistration,
)
from ten_u_event_trend_data_v1 import HOUR_MS, load_hourly, parse_utc


FOUR_HOURS_MS = 4 * HOUR_MS


@dataclass(frozen=True)
class HourBar:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume_quote: float


@dataclass(frozen=True)
class FourHourBar:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume_quote: float
    true_range: float

    @property
    def close_ts(self) -> int:
        return self.ts + FOUR_HOURS_MS


@dataclass(frozen=True)
class FundingPoint:
    ts: int
    realized_rate: float


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    contract_value_base: float
    lot_size_contracts: float
    minimum_contracts: float

    def round_notional(self, requested: float, price: float) -> tuple[float, float]:
        raw_contracts = requested / (price * self.contract_value_base)
        contracts = math.floor((raw_contracts + 1e-12) / self.lot_size_contracts) * self.lot_size_contracts
        if contracts + 1e-12 < self.minimum_contracts:
            return 0.0, 0.0
        quantity_base = contracts * self.contract_value_base
        return quantity_base * price, quantity_base


@dataclass(frozen=True)
class Ignition:
    symbol: str
    direction: str
    signal_ts: int
    midpoint: float
    tr_ratio: float
    volume_ratio: float

    @property
    def score(self) -> float:
        return min(self.tr_ratio, self.volume_ratio)


@dataclass(frozen=True)
class EntryProposal:
    symbol: str
    direction: str
    ignition_ts: int
    entry_ts: int
    structural_invalidation: float
    atr_1h: float
    score: float


def _iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def load_bars(path: Path) -> list[HourBar]:
    return [
        HourBar(
            ts=item.timestamp_ms,
            open=float(item.open),
            high=float(item.high),
            low=float(item.low),
            close=float(item.close),
            volume_quote=float(item.volume_quote),
        )
        for item in load_hourly(path)
    ]


def load_funding(path: Path) -> list[FundingPoint]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        points = [
            FundingPoint(int(row["timestamp_ms"]), float(row["realized_rate"]))
            for row in csv.DictReader(handle)
        ]
    if [point.ts for point in points] != sorted({point.ts for point in points}):
        raise ValueError(f"funding timestamps are not unique and ordered: {path}")
    return points


def aggregate_four_hour(bars: list[HourBar]) -> list[FourHourBar]:
    groups: dict[int, list[HourBar]] = {}
    for bar in bars:
        start = bar.ts - (bar.ts % FOUR_HOURS_MS)
        groups.setdefault(start, []).append(bar)
    raw: list[tuple[int, list[HourBar]]] = []
    for start, chunk in sorted(groups.items()):
        chunk.sort(key=lambda item: item.ts)
        if [item.ts for item in chunk] != [start + offset * HOUR_MS for offset in range(4)]:
            continue
        raw.append((start, chunk))
    result: list[FourHourBar] = []
    prior_close: float | None = None
    for start, chunk in raw:
        high = max(item.high for item in chunk)
        low = min(item.low for item in chunk)
        true_range = high - low if prior_close is None else max(
            high - low, abs(high - prior_close), abs(low - prior_close)
        )
        result.append(
            FourHourBar(
                ts=start,
                open=chunk[0].open,
                high=high,
                low=low,
                close=chunk[-1].close,
                volume_quote=sum(item.volume_quote for item in chunk),
                true_range=true_range,
            )
        )
        prior_close = chunk[-1].close
    return result


def wilder_atr(bars: list[HourBar], period: int) -> list[float | None]:
    true_ranges: list[float] = []
    for index, bar in enumerate(bars):
        prior_close = bars[index - 1].close if index else bar.open
        true_ranges.append(max(bar.high - bar.low, abs(bar.high - prior_close), abs(bar.low - prior_close)))
    output: list[float | None] = [None] * len(bars)
    if len(bars) < period:
        return output
    value = sum(true_ranges[:period]) / period
    output[period - 1] = value
    for index in range(period, len(bars)):
        value = ((period - 1) * value + true_ranges[index]) / period
        output[index] = value
    return output


def find_ignitions(
    symbol: str,
    four_hour: list[FourHourBar],
    config: EventTrendConfig,
    start_ms: int,
    end_ms: int,
) -> list[Ignition]:
    result: list[Ignition] = []
    lookback = config.baseline_4h_bars
    for index in range(lookback, len(four_hour)):
        bar = four_hour[index]
        if not start_ms <= bar.close_ts < end_ms:
            continue
        prior = four_hour[index - lookback : index]
        tr_baseline = median(item.true_range for item in prior)
        volume_baseline = median(item.volume_quote for item in prior)
        if tr_baseline <= 0 or volume_baseline <= 0 or bar.high <= bar.low:
            continue
        tr_ratio = bar.true_range / tr_baseline
        volume_ratio = bar.volume_quote / volume_baseline
        if tr_ratio < float(config.true_range_median_multiple) or volume_ratio < float(
            config.quote_volume_median_multiple
        ):
            continue
        close_location = (bar.close - bar.low) / (bar.high - bar.low)
        prior_range = four_hour[index - config.prior_range_break_4h_bars : index]
        direction: str | None = None
        if (
            close_location >= float(config.close_location_long_min)
            and bar.high > max(item.high for item in prior_range)
        ):
            direction = "long"
        elif (
            close_location <= float(config.close_location_short_max)
            and bar.low < min(item.low for item in prior_range)
        ):
            direction = "short"
        if direction:
            result.append(
                Ignition(
                    symbol=symbol,
                    direction=direction,
                    signal_ts=bar.close_ts,
                    midpoint=(bar.high + bar.low) / 2,
                    tr_ratio=tr_ratio,
                    volume_ratio=volume_ratio,
                )
            )
    return result


def build_entry_proposals(
    symbol: str,
    bars: list[HourBar],
    ignitions: list[Ignition],
    config: EventTrendConfig,
    phase_end_ms: int,
) -> list[EntryProposal]:
    timestamps = [bar.ts for bar in bars]
    atr = wilder_atr(bars, config.atr_1h_period)
    proposals: list[EntryProposal] = []
    for ignition in ignitions:
        start = bisect_left(timestamps, ignition.signal_ts)
        saw_counter = False
        lows: list[float] = []
        highs: list[float] = []
        for index in range(start, min(start + config.pullback_wait_hours, len(bars))):
            bar = bars[index]
            if bar.ts >= phase_end_ms:
                break
            previous = bars[index - 1] if index else bar
            lows.append(bar.low)
            highs.append(bar.high)
            if ignition.direction == "long":
                if bar.close < ignition.midpoint:
                    break
                saw_counter = saw_counter or bar.close < previous.close
                resumed = saw_counter and bar.close > previous.high
                structural = min(lows)
            else:
                if bar.close > ignition.midpoint:
                    break
                saw_counter = saw_counter or bar.close > previous.close
                resumed = saw_counter and bar.close < previous.low
                structural = max(highs)
            if not resumed or atr[index] is None or index + 1 >= len(bars):
                continue
            entry_ts = bars[index + 1].ts
            if entry_ts >= phase_end_ms:
                break
            proposals.append(
                EntryProposal(
                    symbol=symbol,
                    direction=ignition.direction,
                    ignition_ts=ignition.signal_ts,
                    entry_ts=entry_ts,
                    structural_invalidation=structural,
                    atr_1h=float(atr[index]),
                    score=ignition.score,
                )
            )
            break
    return proposals


def _exit_execution(raw_price: float, direction: str, slippage: float) -> float:
    return raw_price * (1 - slippage if direction == "long" else 1 + slippage)


def _entry_execution(raw_price: float, direction: str, slippage: float) -> float:
    return raw_price * (1 + slippage if direction == "long" else 1 - slippage)


def _hard_stop_fill_raw(bar: HourBar, direction: str, hard_stop_raw: float) -> float:
    """Conservative stop-market fill before applying explicit slippage."""
    if direction == "long":
        return min(hard_stop_raw, bar.open)
    return max(hard_stop_raw, bar.open)


def simulate_trade(
    proposal: EntryProposal,
    bars: list[HourBar],
    funding: list[FundingPoint],
    spec: InstrumentSpec,
    config: EventTrendConfig,
    equity: float,
    phase_end_ms: int,
) -> dict[str, Any]:
    timestamps = [bar.ts for bar in bars]
    entry_index = bisect_left(timestamps, proposal.entry_ts)
    if entry_index >= len(bars) or bars[entry_index].ts != proposal.entry_ts:
        return {"accepted": False, "reason": "missing_entry_bar"}
    entry_bar = bars[entry_index]
    entry_raw = entry_bar.open
    if proposal.direction == "long":
        hard_stop_raw = proposal.structural_invalidation - float(
            config.disaster_stop_buffer_atr
        ) * proposal.atr_1h
        if hard_stop_raw <= 0 or hard_stop_raw >= entry_raw:
            return {"accepted": False, "reason": "invalid_long_stop"}
    else:
        hard_stop_raw = proposal.structural_invalidation + float(
            config.disaster_stop_buffer_atr
        ) * proposal.atr_1h
        if hard_stop_raw <= entry_raw:
            return {"accepted": False, "reason": "invalid_short_stop"}
    stop_distance = abs(entry_raw - hard_stop_raw) / entry_raw
    if stop_distance > float(config.maximum_disaster_stop_distance):
        return {"accepted": False, "reason": "stop_too_wide", "stop_distance": stop_distance}

    fee = float(config.taker_fee_each_side)
    slip = float(config.slippage_each_side)
    risk_denominator = stop_distance + 2 * (fee + slip)
    requested = min(
        equity * float(config.maximum_effective_leverage),
        equity * float(config.risk_per_trade) / risk_denominator,
    )
    entry_exec = _entry_execution(entry_raw, proposal.direction, slip)
    notional, quantity = spec.round_notional(requested, entry_exec)
    if notional <= 0 or quantity <= 0:
        return {"accepted": False, "reason": "below_contract_minimum"}

    four = aggregate_four_hour(bars)
    four_by_close = {item.close_ts: (idx, item) for idx, item in enumerate(four)}
    pending_exit: str | None = None
    exit_raw: float | None = None
    exit_index: int | None = None
    exit_reason: str | None = None
    mfe_price = entry_raw
    mae_price = entry_raw
    marks: list[dict[str, float | int]] = []
    time_exit = proposal.entry_ts + config.maximum_holding_hours * HOUR_MS
    funding_by_ts = {point.ts: point.realized_rate for point in funding}
    accrued_funding = 0.0
    entry_fee = notional * fee

    for index in range(entry_index, len(bars)):
        bar = bars[index]
        if bar.ts >= phase_end_ms:
            break
        if pending_exit is not None or bar.ts >= time_exit:
            exit_raw = bar.open
            exit_index = index
            exit_reason = pending_exit or "time_48h"
            break

        if proposal.direction == "long":
            mfe_price = max(mfe_price, bar.high)
            mae_price = min(mae_price, bar.low)
            hard_hit = bar.low <= hard_stop_raw
        else:
            mfe_price = min(mfe_price, bar.low)
            mae_price = max(mae_price, bar.high)
            hard_hit = bar.high >= hard_stop_raw
        if hard_hit:
            exit_raw = _hard_stop_fill_raw(bar, proposal.direction, hard_stop_raw)
            exit_index = index
            exit_reason = "hard_disaster_stop"
            break

        if proposal.entry_ts < bar.ts <= phase_end_ms and bar.ts in funding_by_ts:
            signed = -1.0 if proposal.direction == "long" else 1.0
            accrued_funding += signed * quantity * bar.open * funding_by_ts[bar.ts]

        mark_price = bar.close
        mark_exit_exec = _exit_execution(mark_price, proposal.direction, slip)
        mark_price_pnl = (
            (mark_exit_exec - entry_exec) * quantity
            if proposal.direction == "long"
            else (entry_exec - mark_exit_exec) * quantity
        )
        mark_exit_fee = quantity * mark_exit_exec * fee
        marks.append(
            {
                "ts": bar.ts + HOUR_MS,
                # Marked equity is executable liquidation equity, including
                # the estimated closing slippage and fee at this bar close.
                "equity": equity
                + mark_price_pnl
                - entry_fee
                - mark_exit_fee
                + accrued_funding,
            }
        )

        structural_broken = (
            bar.close < proposal.structural_invalidation
            if proposal.direction == "long"
            else bar.close > proposal.structural_invalidation
        )
        if structural_broken:
            pending_exit = "structural_close_invalidation"
            continue

        close_ts = bar.ts + HOUR_MS
        held_hours = (close_ts - proposal.entry_ts) // HOUR_MS
        if held_hours >= config.minimum_holding_before_trailing_hours and close_ts in four_by_close:
            four_index, current_four = four_by_close[close_ts]
            if four_index > 0:
                prior_four = four[four_index - 1]
                trailing_broken = (
                    current_four.close < prior_four.low
                    if proposal.direction == "long"
                    else current_four.close > prior_four.high
                )
                if trailing_broken:
                    pending_exit = "four_hour_structure_trail"

    if exit_raw is None:
        last_index = bisect_left(timestamps, phase_end_ms) - 1
        if last_index < entry_index:
            return {"accepted": False, "reason": "no_exit_bar"}
        exit_index = last_index
        exit_raw = bars[last_index].close
        exit_reason = "formation_boundary"

    exit_ts = bars[exit_index].ts if exit_reason != "formation_boundary" else phase_end_ms
    exit_exec = _exit_execution(exit_raw, proposal.direction, slip)
    # Funding at the exact exit timestamp is not charged: the replay exits at
    # that timestamp's open before settlement. Other settlements were accrued
    # causally while the position was held.
    exit_notional = quantity * exit_exec
    exit_fee = exit_notional * fee
    price_pnl = (
        (exit_exec - entry_exec) * quantity
        if proposal.direction == "long"
        else (entry_exec - exit_exec) * quantity
    )
    net_pnl = price_pnl - entry_fee - exit_fee + accrued_funding
    raw_price_pnl = (
        (exit_raw - entry_raw) * quantity
        if proposal.direction == "long"
        else (entry_raw - exit_raw) * quantity
    )
    slippage_cost = raw_price_pnl - price_pnl
    favorable_pnl = (
        (mfe_price - entry_raw) * quantity
        if proposal.direction == "long"
        else (entry_raw - mfe_price) * quantity
    )
    price_capture = (
        max(0.0, min(1.0, raw_price_pnl / favorable_pnl))
        if raw_price_pnl > 0 and favorable_pnl > 0
        else None
    )
    net_capture = (
        max(0.0, min(1.0, net_pnl / favorable_pnl))
        if net_pnl > 0 and favorable_pnl > 0
        else None
    )
    r_price = abs(entry_raw - hard_stop_raw)
    recovery_end = min(phase_end_ms, time_exit)
    hard_stop_recovered_entry = False
    hard_stop_recovered_1r = False
    structure_exit_recovered_entry = False
    hard_stop_recovery_entry_ts: int | None = None
    hard_stop_recovery_1r_ts: int | None = None
    structure_exit_recovery_entry_ts: int | None = None
    if exit_reason == "hard_disaster_stop" or exit_reason in {
        "structural_close_invalidation",
        "four_hour_structure_trail",
    }:
        for bar in bars[exit_index + 1 : bisect_left(timestamps, recovery_end)]:
            reached_entry = (
                bar.high >= entry_raw
                if proposal.direction == "long"
                else bar.low <= entry_raw
            )
            reached_1r = (
                bar.high >= entry_raw + r_price
                if proposal.direction == "long"
                else bar.low <= entry_raw - r_price
            )
            if exit_reason == "hard_disaster_stop":
                if reached_entry and not hard_stop_recovered_entry:
                    hard_stop_recovered_entry = True
                    hard_stop_recovery_entry_ts = bar.ts
                if reached_1r and not hard_stop_recovered_1r:
                    hard_stop_recovered_1r = True
                    hard_stop_recovery_1r_ts = bar.ts
                if hard_stop_recovered_1r:
                    break
            elif reached_entry:
                structure_exit_recovered_entry = True
                structure_exit_recovery_entry_ts = bar.ts
                break
    return {
        "accepted": True,
        "symbol": proposal.symbol,
        "direction": proposal.direction,
        "ignition_ts": proposal.ignition_ts,
        "entry_ts": proposal.entry_ts,
        "exit_ts": exit_ts,
        "entry_time": _iso(proposal.entry_ts),
        "exit_time": _iso(exit_ts),
        "entry_raw": entry_raw,
        "entry_exec": entry_exec,
        "exit_raw": exit_raw,
        "exit_exec": exit_exec,
        "structural_invalidation": proposal.structural_invalidation,
        "hard_stop": hard_stop_raw,
        "stop_distance_fraction": stop_distance,
        "notional": notional,
        "quantity_base": quantity,
        "raw_price_pnl": raw_price_pnl,
        "price_pnl_after_slippage": price_pnl,
        "fees": entry_fee + exit_fee,
        "slippage_cost": slippage_cost,
        "funding_pnl": accrued_funding,
        "net_pnl": net_pnl,
        "exit_reason": exit_reason,
        "holding_hours": (exit_ts - proposal.entry_ts) / HOUR_MS,
        "mfe_price": mfe_price,
        "mae_price": mae_price,
        # Price capture measures giveback from favorable price excursion and
        # deliberately excludes funding; net capture is retained diagnostically.
        "winner_capture_fraction": price_capture,
        "net_winner_capture_fraction": net_capture,
        "hard_stop_recovered_entry": hard_stop_recovered_entry,
        "hard_stop_recovered_1r": hard_stop_recovered_1r,
        "hard_stop_recovery_entry_ts": hard_stop_recovery_entry_ts,
        "hard_stop_recovery_1r_ts": hard_stop_recovery_1r_ts,
        "hard_stop_recovery_entry_hours": (
            (hard_stop_recovery_entry_ts - exit_ts) / HOUR_MS
            if hard_stop_recovery_entry_ts is not None
            else None
        ),
        "structure_exit_recovered_entry": structure_exit_recovered_entry,
        "structure_exit_recovery_entry_ts": structure_exit_recovery_entry_ts,
        "stopped_then_recovered_1r": hard_stop_recovered_1r,
        "marks": marks,
    }


def evaluate_gate(report: dict[str, Any], gate: EventTrendFormationGate) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if report["trades"] < gate.minimum_trades:
        reasons.append("trades_below_minimum")
    if report["trades_by_symbol"].get("RAVE-USDT-SWAP", 0) < gate.minimum_rave_trades:
        reasons.append("rave_trades_below_minimum")
    if report["trades_by_symbol"].get("LAB-USDT-SWAP", 0) < gate.minimum_lab_trades:
        reasons.append("lab_trades_below_minimum")
    if report["profit_factor"] < float(gate.minimum_profit_factor):
        reasons.append("profit_factor_below_minimum")
    if report["ending_equity"] < float(gate.minimum_ending_equity):
        reasons.append("ending_equity_below_minimum")
    if report["peak_equity"] < float(gate.minimum_peak_equity):
        reasons.append("peak_equity_below_minimum")
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
    if report["top_trade_gross_profit_contribution"] > float(
        gate.maximum_top_trade_gross_profit_contribution
    ):
        reasons.append("top_trade_concentration_above_maximum")
    return not reasons, reasons


def run_variant(
    config: EventTrendConfig,
    bars_by_symbol: dict[str, list[HourBar]],
    funding_by_symbol: dict[str, list[FundingPoint]],
    specs: dict[str, InstrumentSpec],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    proposals: list[EntryProposal] = []
    ignition_counts: dict[str, int] = {}
    proposal_counts: dict[str, int] = {}
    for symbol in config.symbols:
        bars = bars_by_symbol[symbol]
        ignitions = find_ignitions(symbol, aggregate_four_hour(bars), config, start_ms, end_ms)
        symbol_proposals = build_entry_proposals(symbol, bars, ignitions, config, end_ms)
        proposals.extend(symbol_proposals)
        ignition_counts[symbol] = len(ignitions)
        proposal_counts[symbol] = len(symbol_proposals)
    proposals.sort(key=lambda item: (item.entry_ts, -item.score, item.symbol))

    equity = float(config.initial_equity)
    peak_realized = equity
    peak_marked = equity
    max_drawdown = 0.0
    permanent_state: str | None = None
    cooldown_until = 0
    consecutive_losses = 0
    daily_date: str | None = None
    daily_start_equity = equity
    daily_halt_date: str | None = None
    available_after = start_ms
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
            skipped.extend({"entry_ts": timestamp, "symbol": p.symbol, "reason": "signal_during_open"} for p in group)
            continue
        date = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()
        if date != daily_date:
            daily_date = date
            daily_start_equity = equity
            daily_halt_date = None
        if permanent_state:
            skipped.extend({"entry_ts": timestamp, "symbol": p.symbol, "reason": permanent_state} for p in group)
            continue
        if timestamp < cooldown_until:
            skipped.extend({"entry_ts": timestamp, "symbol": p.symbol, "reason": "cooldown"} for p in group)
            continue
        if daily_halt_date == date:
            skipped.extend({"entry_ts": timestamp, "symbol": p.symbol, "reason": "daily_loss_halt"} for p in group)
            continue

        ranked = sorted(group, key=lambda item: (-item.score, item.symbol))
        proposal: EntryProposal | None = None
        trade: dict[str, Any] | None = None
        for candidate in ranked:
            candidate_trade = simulate_trade(
                candidate,
                bars_by_symbol[candidate.symbol],
                funding_by_symbol[candidate.symbol],
                specs[candidate.symbol],
                config,
                equity,
                end_ms,
            )
            if candidate_trade["accepted"]:
                proposal, trade = candidate, candidate_trade
                break
            skipped.append({"entry_ts": timestamp, "symbol": candidate.symbol, **candidate_trade})
        if proposal is None or trade is None:
            continue
        skipped.extend(
            {"entry_ts": timestamp, "symbol": candidate.symbol, "reason": "same_timestamp_arbitration"}
            for candidate in ranked[ranked.index(proposal) + 1 :]
        )
        before = equity
        for mark in trade.pop("marks"):
            peak_marked = max(peak_marked, float(mark["equity"]))
            if peak_marked > 0:
                max_drawdown = max(max_drawdown, (peak_marked - float(mark["equity"])) / peak_marked)
        equity = max(0.0, equity + trade["net_pnl"])
        trade["equity_before"] = before
        trade["equity_after"] = equity
        accepted.append(trade)
        available_after = trade["exit_ts"]
        peak_realized = max(peak_realized, equity)
        peak_marked = max(peak_marked, equity)
        if peak_marked > 0:
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
            daily_date = exit_date
            daily_start_equity = before
        if daily_start_equity > 0 and (daily_start_equity - equity) / daily_start_equity >= float(
            config.daily_loss_halt
        ):
            daily_halt_date = exit_date
        realized_drawdown = (peak_realized - equity) / peak_realized if peak_realized else 1.0
        if equity <= float(config.ruin_equity):
            permanent_state = "ruined"
        elif realized_drawdown >= float(config.peak_drawdown_halt):
            permanent_state = "peak_drawdown_halt"

    positive = [trade["net_pnl"] for trade in accepted if trade["net_pnl"] > 0]
    negative = [-trade["net_pnl"] for trade in accepted if trade["net_pnl"] < 0]
    hard_stopped = [
        trade for trade in accepted if trade["exit_reason"] == "hard_disaster_stop"
    ]
    structure_exited = [
        trade
        for trade in accepted
        if trade["exit_reason"]
        in {"structural_close_invalidation", "four_hour_structure_trail"}
    ]
    captures = [
        trade["winner_capture_fraction"]
        for trade in accepted
        if trade["winner_capture_fraction"] is not None
    ]
    gross_positive = sum(positive)
    report: dict[str, Any] = {
        "config_fingerprint": config.fingerprint(),
        "formation_start": _iso(start_ms),
        "formation_end": _iso(end_ms),
        "ignitions_by_symbol": ignition_counts,
        "entry_proposals_by_symbol": proposal_counts,
        "starting_equity": float(config.initial_equity),
        "ending_equity": equity,
        "peak_equity": peak_marked,
        "return_fraction": equity / float(config.initial_equity) - 1,
        "max_drawdown_fraction": max_drawdown,
        "trades": len(accepted),
        "wins": len(positive),
        "trades_by_symbol": {
            symbol: sum(trade["symbol"] == symbol for trade in accepted) for symbol in config.symbols
        },
        "profit_factor": gross_positive / sum(negative) if negative else (1_000_000_000.0 if positive else 0.0),
        "profit_factor_is_infinite": bool(positive and not negative),
        "total_fees": sum(trade["fees"] for trade in accepted),
        "total_slippage": sum(trade["slippage_cost"] for trade in accepted),
        "total_funding_pnl": sum(trade["funding_pnl"] for trade in accepted),
        "peak_profit_retention": (
            max(0.0, (equity - float(config.initial_equity)) / (peak_marked - float(config.initial_equity)))
            if peak_marked > float(config.initial_equity)
            else 0.0
        ),
        "hard_stop_count": len(hard_stopped),
        "stopped_then_recovered_fraction": (
            sum(trade["hard_stop_recovered_entry"] for trade in hard_stopped)
            / len(hard_stopped)
            if hard_stopped
            else 0.0
        ),
        "hard_stop_recovered_1r_fraction": (
            sum(trade["hard_stop_recovered_1r"] for trade in hard_stopped)
            / len(hard_stopped)
            if hard_stopped
            else 0.0
        ),
        "structure_exit_recovered_entry_fraction": (
            sum(trade["structure_exit_recovered_entry"] for trade in structure_exited)
            / len(structure_exited)
            if structure_exited
            else 0.0
        ),
        "median_winner_capture": median(captures) if captures else 0.0,
        "top_trade_gross_profit_contribution": max(positive) / gross_positive if positive else 0.0,
        "permanent_account_state": permanent_state or "active_or_temporary_cooldown",
        "skipped": skipped,
        "trades_detail": accepted,
    }
    return report


def run_formation(
    data_dir: Path,
    preregistration_path: Path,
    dataset_manifest_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    saved = json.loads(preregistration_path.read_text(encoding="utf-8"))
    if saved != build_preregistration():
        raise ValueError("saved preregistration does not match the frozen code contract")
    manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("coverage_status") != "PASS":
        raise ValueError("hourly dataset coverage must pass before Formation")
    config = EventTrendConfig()
    gate = EventTrendFormationGate()
    windows = EventTrendResearchWindows()
    start_ms = parse_utc(windows.formation_start)
    end_ms = parse_utc(windows.formation_end)
    bars_by_symbol: dict[str, list[HourBar]] = {}
    funding_by_symbol: dict[str, list[FundingPoint]] = {}
    specs: dict[str, InstrumentSpec] = {}
    funding_coverage: dict[str, Any] = {}
    funding_file_sha256: dict[str, str] = {}
    for symbol in config.symbols:
        manifest_item = manifest["symbols"][symbol]
        candle_path = Path(manifest_item["path"])
        actual_candle_hash = hashlib.sha256(candle_path.read_bytes()).hexdigest()
        if actual_candle_hash != manifest_item["sha256"]:
            raise ValueError(f"hourly dataset fingerprint drift for {symbol}")
        bars_by_symbol[symbol] = load_bars(candle_path)
        funding_path = data_dir / f"{symbol}_funding.csv"
        funding_file_sha256[symbol] = hashlib.sha256(funding_path.read_bytes()).hexdigest()
        funding_by_symbol[symbol] = load_funding(funding_path)
        formation_funding = [point for point in funding_by_symbol[symbol] if start_ms <= point.ts < end_ms]
        maximum_gap_hours = max(
            ((right.ts - left.ts) / HOUR_MS for left, right in zip(formation_funding, formation_funding[1:])),
            default=math.inf,
        )
        boundary_covered = bool(
            formation_funding
            and formation_funding[0].ts <= start_ms + 8 * HOUR_MS
            and formation_funding[-1].ts >= end_ms - 8 * HOUR_MS
        )
        funding_coverage[symbol] = {
            "points": len(formation_funding),
            "first": _iso(formation_funding[0].ts) if formation_funding else None,
            "last": _iso(formation_funding[-1].ts) if formation_funding else None,
            "maximum_gap_hours": maximum_gap_hours,
            "boundary_covered": boundary_covered,
            "status": "PASS" if maximum_gap_hours <= 8 and boundary_covered else "FAIL",
        }
        instrument = manifest_item["instrument"]
        specs[symbol] = InstrumentSpec(
            symbol=symbol,
            contract_value_base=float(instrument["ctVal"]),
            lot_size_contracts=float(instrument["lotSz"]),
            minimum_contracts=float(instrument["minSz"]),
        )
    if any(item["status"] != "PASS" for item in funding_coverage.values()):
        raise ValueError("actual Formation funding coverage is required for every symbol")

    primary = run_variant(
        config, bars_by_symbol, funding_by_symbol, specs, start_ms, end_ms
    )
    gate_pass, gate_reasons = evaluate_gate(primary, gate)
    sensitivity: dict[str, Any] = {}
    for name, changes in config.sensitivity_variants.items():
        typed: dict[str, Any] = {}
        for key, value in changes.items():
            current = getattr(config, key)
            typed[key] = Decimal(value) if isinstance(current, Decimal) else int(value)
        variant_config = replace(config, **typed)
        result = run_variant(
            variant_config, bars_by_symbol, funding_by_symbol, specs, start_ms, end_ms
        )
        variant_pass, variant_reasons = evaluate_gate(result, gate)
        sensitivity[name] = {
            "diagnostic_only": True,
            "may_rescue_primary": False,
            "gate_pass": variant_pass,
            "gate_reasons": variant_reasons,
            "summary": {key: value for key, value in result.items() if key not in {"trades_detail", "skipped"}},
        }

    report: dict[str, Any] = {
        "phase": "formation",
        "formal_status": "formation_pass" if gate_pass else "formation_fail",
        "strategy_id": config.strategy_id,
        "config_fingerprint": config.fingerprint(),
        "formation_gate_fingerprint": gate.fingerprint(),
        "dataset_manifest_sha256": hashlib.sha256(dataset_manifest_path.read_bytes()).hexdigest(),
        "funding_cost_status": "actual_history_applied",
        "funding_coverage": funding_coverage,
        "funding_file_sha256": funding_file_sha256,
        "validation_metrics_accessed": False,
        "contaminated_case_metrics_accessed": False,
        "prospective_oos_metrics_accessed": False,
        "gate_pass": gate_pass,
        "gate_reasons": gate_reasons,
        "primary": primary,
        "sensitivity": sensitivity,
        "decision": (
            "unlock_retrospective_validation_without_parameter_changes"
            if gate_pass
            else "reject_v1_primary_sensitivity_cannot_rescue"
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/event_trend_v1"))
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("reports/ten_u_event_trend_preregistration_v1.json"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/event_trend_v1/hourly_dataset_manifest_v1.json"),
    )
    parser.add_argument(
        "--report", type=Path, default=Path("reports/ten_u_event_trend_formation_v1.json")
    )
    args = parser.parse_args()
    result = run_formation(args.data, args.preregistration, args.manifest, args.report)
    print(json.dumps({key: value for key, value in result.items() if key != "primary"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
