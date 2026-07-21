"""Formation-only runner for the frozen 10U trend-breakout candidate.

This module never evaluates Validation or OOS returns. It binds the amended
research protocol, MarketState v1.1, signal contract, and 10U sleeve into one
deterministic account replay.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from market import Bar, FeatureBar, add_features, load_market, resample_minutes
from market_state import calculate_market_state
from market_state_schema import (
    MarketRegimeState,
    MarketStateConfig,
    generate_snapshot_id,
    get_market_state_config_fingerprint,
)
from research_protocol import (
    ResearchProtocol,
    assess_symbol_coverage,
    enforce_data_cutoff,
)
from ten_u_sleeve_v1 import TenUSleeveAccount, TenUSleeveConfig, TradeEvent
from ten_u_warlord_signal_v1 import (
    BREAKOUT_WINDOW,
    MIN_HISTORY_BARS,
    SignalProposal,
    check_signal,
    get_signal_contract_fingerprint,
)

BAR_MS = 900_000


@dataclass(frozen=True)
class FormationGate:
    min_trades: int = 30
    min_return_pct: Decimal = Decimal("0")
    min_profit_factor: Decimal = Decimal("1.10")
    max_drawdown_pct: Decimal = Decimal("70")
    arbitration: str = "breakout_overshoot_atr_desc_then_symbol"

    def fingerprint(self) -> str:
        payload = {
            "min_trades": self.min_trades,
            "min_return_pct": str(self.min_return_pct),
            "min_profit_factor": str(self.min_profit_factor),
            "max_drawdown_pct": str(self.max_drawdown_pct),
            "arbitration": self.arbitration,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _weekly_monday_utc(bars: list[FeatureBar]) -> list[FeatureBar]:
    groups: dict[int, list[FeatureBar]] = {}
    for bar in bars:
        dt = datetime.fromtimestamp(bar.ts / 1000, tz=timezone.utc)
        monday = (dt - timedelta(
            days=dt.weekday(), hours=dt.hour, minutes=dt.minute,
            seconds=dt.second, microseconds=dt.microsecond,
        ))
        key = int(monday.timestamp() * 1000)
        groups.setdefault(key, []).append(bar)
    raw: list[Bar] = []
    for ts, chunk in sorted(groups.items()):
        # Reject partial weeks. A crypto week has 672 completed 15m bars.
        if len(chunk) < 672 or chunk[0].ts != ts:
            continue
        raw.append(Bar(
            ts=ts,
            time=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            open=chunk[0].open,
            high=max(b.high for b in chunk),
            low=min(b.low for b in chunk),
            close=chunk[-1].close,
            volume_quote=sum(b.volume_quote for b in chunk),
        ))
    return add_features(raw)


def _completed_prefix(
    bars: list[FeatureBar], timestamps: list[int], available_at_ms: int,
    duration_ms: int, limit: int = 300,
) -> list[FeatureBar]:
    count = bisect_right(timestamps, available_at_ms - duration_ms)
    return bars[max(0, count - limit):count]


def _is_raw_breakout(bars: list[FeatureBar], current_idx: int) -> bool:
    if current_idx < MIN_HISTORY_BARS:
        return False
    trigger = bars[current_idx - 1]
    lookback = bars[current_idx - 1 - BREAKOUT_WINDOW:current_idx - 1]
    return (
        trigger.close > max(b.high for b in lookback)
        or trigger.close < min(b.low for b in lookback)
    )


def _proposal_score(proposal: SignalProposal, bars: list[FeatureBar], current_idx: int) -> Decimal:
    lookback = bars[current_idx - 1 - BREAKOUT_WINDOW:current_idx - 1]
    if proposal.direction == "long":
        boundary = Decimal(str(max(b.high for b in lookback)))
        overshoot = proposal.reference_close - boundary
    else:
        boundary = Decimal(str(min(b.low for b in lookback)))
        overshoot = boundary - proposal.reference_close
    return overshoot / proposal.atr


def run_formation(
    data_dir: Path,
    protocol_path: Path,
    report_path: Path | None = None,
) -> dict[str, Any]:
    protocol = ResearchProtocol.load(protocol_path)
    gate = FormationGate(min_trades=protocol.min_formation_trades)
    market = load_market(data_dir, 15, symbols=set(protocol.symbol_universe))
    market, removed = enforce_data_cutoff(
        market, protocol.data_cutoff, bar_duration_ms=BAR_MS
    )
    timeline = sorted({b.ts for bars in market.values() for b in bars})
    boundaries = protocol.split.compute_boundaries(timeline, bar_duration_ms=BAR_MS)
    coverage = assess_symbol_coverage(
        market,
        protocol.symbol_universe,
        boundaries,
        min_trading_bars=260,
        warmup_bars=260,
        bar_duration_ms=BAR_MS,
    )
    base_report: dict[str, Any] = {
        "phase": "formation",
        "strategy_id": "ten_u_trend_breakout_v1",
        "protocol_fingerprint": protocol.config_fingerprint,
        "signal_contract_fingerprint": get_signal_contract_fingerprint(),
        "sleeve_config_fingerprint": "",
        "formation_gate_fingerprint": gate.fingerprint(),
        "market_state_config_fingerprint": get_market_state_config_fingerprint(),
        "formation_start_ts": boundaries.formation_start_ts,
        "formation_end_ts": boundaries.formation_end_ts,
        "validation_metrics_accessed": False,
        "oos_metrics_accessed": False,
        "coverage": coverage,
        "removed_after_cutoff": removed,
        "funding_cost_status": protocol.funding_cost_status,
    }
    if coverage["coverage_status"] != "PASS":
        base_report.update({"formal_status": "data_blocked", "gate_pass": False})
        if report_path:
            report_path.write_text(json.dumps(base_report, indent=2), encoding="utf-8")
        return base_report

    sleeve_config = TenUSleeveConfig.from_research_protocol(protocol)
    account = TenUSleeveAccount(sleeve_config)
    base_report["sleeve_config_fingerprint"] = sleeve_config.fingerprint()
    state_config = MarketStateConfig()

    frames: dict[str, dict[str, list[FeatureBar]]] = {}
    frame_ts: dict[str, dict[str, list[int]]] = {}
    indices: dict[str, dict[int, int]] = {}
    for symbol, bars in market.items():
        h4 = add_features(resample_minutes(bars, 240))
        daily = add_features(resample_minutes(bars, 1440))
        weekly = _weekly_monday_utc(bars)
        frames[symbol] = {"15m": bars, "4h": h4, "1d": daily, "1w": weekly}
        frame_ts[symbol] = {name: [b.ts for b in values] for name, values in frames[symbol].items()}
        indices[symbol] = {bar.ts: i for i, bar in enumerate(bars)}

    formation_timeline = [
        ts for ts in timeline
        if boundaries.formation_start_ts <= ts < boundaries.formation_end_ts
    ]
    position: dict[str, Any] | None = None
    candidate_count = proposal_count = gap_skips = 0
    exits: list[dict[str, Any]] = []

    regime_info = MarketRegimeState().to_dict()
    for step, ts in enumerate(formation_timeline):
        now = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        account.advance_clock(now, step)

        if position is not None:
            symbol = position["symbol"]
            idx = indices[symbol].get(ts)
            if idx is not None:
                bar = market[symbol][idx]
                direction = position["direction"]
                stop = position["stop"]
                target = position["target"]
                exit_price: Decimal | None = None
                exit_reason = ""
                if direction == "long":
                    if Decimal(str(bar.low)) <= stop:
                        exit_price, exit_reason = stop, "stop"
                    elif Decimal(str(bar.high)) >= target:
                        exit_price, exit_reason = target, "target"
                else:
                    if Decimal(str(bar.high)) >= stop:
                        exit_price, exit_reason = stop, "stop"
                    elif Decimal(str(bar.low)) <= target:
                        exit_price, exit_reason = target, "target"
                if exit_price is not None:
                    record = account.process_event(TradeEvent(
                        timestamp=datetime.fromtimestamp((ts + BAR_MS) / 1000, tz=timezone.utc).isoformat(),
                        symbol=symbol,
                        side=direction,
                        entry_price=position["entry"],
                        exit_price=exit_price,
                        stop_price=stop,
                        exit_reason=exit_reason,
                        bar_index=step,
                    ))
                    exits.append(record)
                    position = None
                    continue

        if position is not None or account.state != "ACTIVE":
            continue

        proposals: list[tuple[Decimal, str, SignalProposal]] = []
        for symbol in protocol.symbol_universe:
            idx = indices[symbol].get(ts)
            if idx is None or not _is_raw_breakout(market[symbol], idx):
                continue
            candidate_count += 1
            available_ms = ts
            f = frames[symbol]
            ft = frame_ts[symbol]
            state = calculate_market_state(
                symbol=symbol,
                weekly_bars=_completed_prefix(f["1w"], ft["1w"], available_ms, 604_800_000),
                daily_bars=_completed_prefix(f["1d"], ft["1d"], available_ms, 86_400_000),
                h4_bars=_completed_prefix(f["4h"], ft["4h"], available_ms, 14_400_000),
                m15_bars=_completed_prefix(f["15m"], ft["15m"], available_ms, BAR_MS),
                market_regime_info=regime_info,
                config=state_config,
                available_at=now,
            )
            snapshot_id = generate_snapshot_id(
                symbol, now, get_market_state_config_fingerprint(), state
            )
            proposal = check_signal(
                symbol,
                state,
                market[symbol][max(0, idx - 300):idx],
                snapshot_id,
            )
            if proposal is not None:
                proposal_count += 1
                proposals.append((_proposal_score(proposal, market[symbol], idx), symbol, proposal))

        if not proposals:
            continue
        proposals.sort(key=lambda item: (-item[0], item[1]))
        _, symbol, proposal = proposals[0]
        entry_bar = market[symbol][indices[symbol][ts]]
        entry = Decimal(str(entry_bar.open))
        if proposal.direction == "long":
            valid_gap = proposal.stop_price < entry < proposal.target_price
        else:
            valid_gap = proposal.target_price < entry < proposal.stop_price
        if not valid_gap:
            gap_skips += 1
            continue
        position = {
            "symbol": symbol,
            "direction": proposal.direction,
            "entry": entry,
            "stop": proposal.stop_price,
            "target": proposal.target_price,
            "entry_ts": ts,
            "signal_fingerprint": proposal.signal_fingerprint,
        }

    if position is not None:
        symbol = position["symbol"]
        eligible = [b for b in market[symbol] if b.ts < boundaries.formation_end_ts]
        if eligible:
            last = eligible[-1]
            record = account.process_event(TradeEvent(
                timestamp=datetime.fromtimestamp((last.ts + BAR_MS) / 1000, tz=timezone.utc).isoformat(),
                symbol=symbol,
                side=position["direction"],
                entry_price=position["entry"],
                exit_price=Decimal(str(last.close)),
                stop_price=position["stop"],
                exit_reason="formation_end",
                bar_index=len(formation_timeline),
            ))
            exits.append(record)

    accepted = account.accepted_trades
    profits = sum((Decimal(t["net_pnl"]) for t in accepted if Decimal(t["net_pnl"]) > 0), Decimal("0"))
    losses = -sum((Decimal(t["net_pnl"]) for t in accepted if Decimal(t["net_pnl"]) < 0), Decimal("0"))
    profit_factor = profits / losses if losses > 0 else Decimal("999") if profits > 0 else Decimal("0")
    return_pct = (account.equity / sleeve_config.initial_equity - Decimal("1")) * Decimal("100")
    max_dd_pct = account.max_drawdown * Decimal("100")
    gate_reasons: list[str] = []
    if len(accepted) < gate.min_trades:
        gate_reasons.append("insufficient_trades")
    if return_pct <= gate.min_return_pct:
        gate_reasons.append("non_positive_return")
    if profit_factor < gate.min_profit_factor:
        gate_reasons.append("profit_factor_below_1_10")
    if max_dd_pct >= gate.max_drawdown_pct:
        gate_reasons.append("drawdown_limit_reached")
    if account.state in ("RUINED", "HALTED_DRAWDOWN"):
        gate_reasons.append("terminal_risk_state")

    base_report.update({
        "formal_status": "formation_pass" if not gate_reasons else "formation_fail",
        "gate_pass": not gate_reasons,
        "gate_reasons": gate_reasons,
        "candidate_breakouts": candidate_count,
        "routed_proposals": proposal_count,
        "gap_skips": gap_skips,
        "starting_equity": str(sleeve_config.initial_equity),
        "ending_equity": str(account.equity),
        "return_pct": str(return_pct.quantize(Decimal("0.0001"))),
        "max_drawdown_pct": str(max_dd_pct.quantize(Decimal("0.0001"))),
        "trades": len(accepted),
        "wins": sum(Decimal(t["net_pnl"]) > 0 for t in accepted),
        "profit_factor": str(profit_factor.quantize(Decimal("0.0001"))),
        "total_fees": str(account.total_fees.quantize(Decimal("0.0001"))),
        "total_slippage": str(account.total_slippage.quantize(Decimal("0.0001"))),
        "account_state": account.state,
        "state_transitions": account.state_transitions,
        "trades_detail": accepted,
    })
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(base_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return base_report


if __name__ == "__main__":
    result = run_formation(
        Path("data"),
        Path("reports/research_protocol_v1.json"),
        Path("reports/ten_u_warlord_formation_v1.json"),
    )
    print(json.dumps({
        key: result.get(key)
        for key in (
            "formal_status", "trades", "return_pct", "profit_factor",
            "max_drawdown_pct", "gate_reasons",
        )
    }, ensure_ascii=False))
