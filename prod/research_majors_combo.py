"""Combo research: does multi-rule allocation beat the admitted single sleeve?

Two frozen protocols (no parameter search):

1. **independent_equal_weight** — each leg runs its own full account at 10U;
   portfolio return is equal-weight average of leg returns (capital split model).

2. **priority_single_slot** — same timeframe only; at most one open position;
   first leg in priority order that signals enters; exits use that leg's risk
   parameters.

Not paper admission. Not demo/live.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from market import load_market
from prod.majors_account_replay import (
    _OpenPos,
    _one_way_cost_rate,
    _size_position,
    replay_majors_account,
    resolve_entry_signal,
)
from prod.majors_contract import (
    MajorsSleeveConfig,
    h1_high_vol_donchian_short_config,
)
from prod.policy import DEFAULT_START_EQUITY_USDT
from prod.research_batch_majors_v6 import research_catalog_v6
from prod.research_batch_majors_v7 import research_catalog_v7


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _summary_from_replay(report: dict[str, Any]) -> dict[str, Any]:
    account = report.get("account") or {}
    start = float(account.get("starting_equity") or 0)
    end = float(account.get("ending_equity") or 0)
    ret = (end / start - 1.0) if start > 0 else None
    return {
        "formal_status": report.get("formal_status"),
        "strategy_id": report.get("strategy_id"),
        "trades": account.get("trades"),
        "return_fraction": ret,
        "ending_equity": end,
        "profit_factor": account.get("profit_factor"),
        "max_drawdown_fraction": account.get("max_drawdown_fraction"),
        "permanent_account_state": account.get("permanent_account_state"),
        "bars": report.get("bars_common"),
    }


@dataclass(frozen=True)
class ComboLeg:
    name: str
    config: MajorsSleeveConfig
    role: str  # primary | secondary | watchlist


def combo_legs_catalog() -> dict[str, ComboLeg]:
    """Named legs used in the combo experiment."""
    v7 = {c["name"]: c for c in research_catalog_v7()}
    v6 = {c["name"]: c for c in research_catalog_v6()}

    def from_v7(name: str, role: str) -> ComboLeg:
        return ComboLeg(name=name, config=v7[name]["config"], role=role)

    def from_v6(name: str, role: str) -> ComboLeg:
        return ComboLeg(name=name, config=v6[name]["config"], role=role)

    primary = ComboLeg(
        name="h1_high_vol_donchian_short",
        config=h1_high_vol_donchian_short_config(),
        role="primary",
    )
    return {
        primary.name: primary,
        "h1_failed_breakout_short": from_v7("h1_failed_breakout_short", "secondary"),
        "h1_failed_breakdown_long": from_v7("h1_failed_breakdown_long", "secondary"),
        "h4_weekly_mom_short": from_v6("h4_weekly_mom_short", "watchlist"),
        "h4_high_vol_donchian_short": from_v7("h4_high_vol_donchian_short", "watchlist"),
        "m15_failed_breakout_short": from_v7("m15_failed_breakout_short", "watchlist"),
    }


def _independent_equal_weight(
    data_dir: Path,
    legs: list[ComboLeg],
    *,
    start_equity: float,
) -> dict[str, Any]:
    leg_summaries: list[dict[str, Any]] = []
    for leg in legs:
        rep = replay_majors_account(
            data_dir, config=leg.config, start_equity=start_equity
        )
        s = _summary_from_replay(rep)
        s["name"] = leg.name
        s["role"] = leg.role
        s["timeframe_minutes"] = leg.config.timeframe_minutes
        leg_summaries.append(s)

    rets = [s["return_fraction"] for s in leg_summaries]
    if any(r is None for r in rets) or any(
        s.get("formal_status") != "ok" for s in leg_summaries
    ):
        return {
            "protocol": "independent_equal_weight",
            "formal_status": "fail",
            "legs": leg_summaries,
            "portfolio": None,
        }

    n = len(rets)
    port_ret = sum(float(r) for r in rets) / n
    # Path-independent DD/PF unavailable; report average metrics as soft stats
    avg_pf = sum(float(s["profit_factor"] or 0) for s in leg_summaries) / n
    # Conservative portfolio DD: max of legs (worst concurrent)
    max_dd = max(float(s["max_drawdown_fraction"] or 0) for s in leg_summaries)
    ending = start_equity * (1.0 + port_ret)
    primary = next((s for s in leg_summaries if s["role"] == "primary"), leg_summaries[0])
    prim_ret = float(primary["return_fraction"] or 0)
    return {
        "protocol": "independent_equal_weight",
        "formal_status": "ok",
        "legs": leg_summaries,
        "portfolio": {
            "return_fraction": port_ret,
            "ending_equity": ending,
            "avg_leg_profit_factor": avg_pf,
            "max_leg_drawdown_fraction": max_dd,
            "beats_primary_return": port_ret > prim_ret + 1e-12,
            "primary_return": prim_ret,
            "return_edge_vs_primary": port_ret - prim_ret,
            "trades_sum": sum(int(s.get("trades") or 0) for s in leg_summaries),
            "notes": (
                "Equal-weight of independent full-sample returns. "
                "Not a path-shared account; DD is max of legs (conservative)."
            ),
        },
    }


def _replay_priority_with_dd(
    data_dir: Path,
    legs: list[ComboLeg],
    *,
    start_equity: float,
) -> dict[str, Any]:
    """Priority single-slot with proper max DD tracking."""
    if not legs:
        return {"formal_status": "fail", "error": "no_legs"}
    tfs = {int(l.config.timeframe_minutes) for l in legs}
    if len(tfs) != 1:
        return {
            "formal_status": "fail",
            "error": "priority_requires_same_timeframe",
            "timeframes": sorted(tfs),
        }
    tf = next(iter(tfs))
    risk_cfg = next((l.config for l in legs if l.role == "primary"), legs[0].config)
    market = load_market(
        data_dir, tf, symbols={"BTC-USDT-SWAP", "ETH-USDT-SWAP"}
    )
    if len(market) < 2:
        return {"formal_status": "data_missing"}

    ts_sets = [{b.ts for b in bars} for bars in market.values()]
    common = sorted(set.intersection(*ts_sets))
    index = {sym: {b.ts: i for i, b in enumerate(bars)} for sym, bars in market.items()}
    run_symbols = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")

    equity = float(start_equity)
    peak = equity
    max_dd = 0.0
    open_pos: _OpenPos | None = None
    open_leg: str | None = None
    open_cfg: MajorsSleeveConfig | None = None
    trades: list[dict[str, Any]] = []
    permanent = "active"
    entries_by_leg: dict[str, int] = {l.name: 0 for l in legs}

    def _mark_dd() -> None:
        nonlocal max_dd, peak
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, 1.0 - equity / peak)

    for ts in common:
        if open_pos is not None and open_cfg is not None:
            bars = market[open_pos.symbol]
            i = index[open_pos.symbol][ts]
            bar = bars[i]
            cost_rate = _one_way_cost_rate(open_cfg)
            exit_price = None
            exit_reason = None
            direction = int(open_pos.direction)
            if direction >= 0:
                if bar.low <= open_pos.stop:
                    exit_price, exit_reason = open_pos.stop, "stop"
                elif bar.high >= open_pos.take_profit:
                    exit_price, exit_reason = open_pos.take_profit, "take_profit"
                else:
                    new_trail = bar.close - open_cfg.trailing_atr * bar.atr
                    if new_trail > open_pos.trail:
                        open_pos.trail = new_trail
                        open_pos.stop = max(open_pos.stop, new_trail)
                    if i - open_pos.entry_idx >= open_cfg.max_hold_bars:
                        exit_price, exit_reason = bar.close, "time_stop"
            else:
                if bar.high >= open_pos.stop:
                    exit_price, exit_reason = open_pos.stop, "stop"
                elif bar.low <= open_pos.take_profit:
                    exit_price, exit_reason = open_pos.take_profit, "take_profit"
                else:
                    new_trail = bar.close + open_cfg.trailing_atr * bar.atr
                    if new_trail < open_pos.trail:
                        open_pos.trail = new_trail
                        open_pos.stop = min(open_pos.stop, new_trail)
                    if i - open_pos.entry_idx >= open_cfg.max_hold_bars:
                        exit_price, exit_reason = bar.close, "time_stop"

            if exit_price is not None:
                if direction >= 0:
                    fill = exit_price * (1.0 - cost_rate)
                    pnl = (fill - open_pos.entry_price) * open_pos.qty
                    dir_label = "long"
                else:
                    fill = exit_price * (1.0 + cost_rate)
                    pnl = (open_pos.entry_price - fill) * open_pos.qty
                    dir_label = "short"
                equity = max(0.0, equity + pnl)
                _mark_dd()
                trades.append(
                    {
                        "leg": open_leg,
                        "symbol": open_pos.symbol,
                        "direction": dir_label,
                        "net_pnl": pnl,
                        "exit_reason": exit_reason,
                    }
                )
                open_pos = None
                open_leg = None
                open_cfg = None
                if equity <= risk_cfg.ruin_equity:
                    permanent = "ruined"
                    break
                if max_dd >= risk_cfg.peak_drawdown_halt:
                    permanent = "peak_drawdown_halt"
                    break

        if open_pos is not None or permanent != "active":
            continue

        for leg in legs:
            resolved = resolve_entry_signal(
                market, index, ts, leg.config, run_symbols, funding_filter="none"
            )
            if resolved is None:
                continue
            sym, direction = resolved
            i = index[sym][ts]
            bar = market[sym][i]
            cost_rate = _one_way_cost_rate(leg.config)
            if direction > 0:
                raw_entry = bar.close * (1.0 + cost_rate)
                stop = raw_entry - leg.config.stop_atr * bar.atr
                tp = raw_entry + leg.config.take_profit_atr * bar.atr
            else:
                raw_entry = bar.close * (1.0 - cost_rate)
                stop = raw_entry + leg.config.stop_atr * bar.atr
                tp = raw_entry - leg.config.take_profit_atr * bar.atr
            sized = _size_position(equity, raw_entry, stop, leg.config)
            if sized is None:
                continue
            qty, notional, margin = sized
            open_pos = _OpenPos(
                symbol=sym,
                direction=int(direction),
                entry_idx=i,
                entry_price=raw_entry,
                qty=qty,
                notional=notional,
                margin=margin,
                stop=stop,
                take_profit=tp,
                trail=stop,
                entry_equity=equity,
            )
            open_leg = leg.name
            open_cfg = leg.config
            entries_by_leg[leg.name] = entries_by_leg.get(leg.name, 0) + 1
            break

    if open_pos is not None and open_cfg is not None and permanent == "active":
        bars = market[open_pos.symbol]
        bar = bars[-1]
        cost_rate = _one_way_cost_rate(open_cfg)
        if open_pos.direction >= 0:
            fill = bar.close * (1.0 - cost_rate)
            pnl = (fill - open_pos.entry_price) * open_pos.qty
            dir_label = "long"
        else:
            fill = bar.close * (1.0 + cost_rate)
            pnl = (open_pos.entry_price - fill) * open_pos.qty
            dir_label = "short"
        equity = max(0.0, equity + pnl)
        _mark_dd()
        trades.append(
            {
                "leg": open_leg,
                "symbol": open_pos.symbol,
                "direction": dir_label,
                "net_pnl": pnl,
                "exit_reason": "end_of_data",
            }
        )

    wins = [t for t in trades if float(t["net_pnl"]) > 0]
    losses = [t for t in trades if float(t["net_pnl"]) <= 0]
    gp = sum(float(t["net_pnl"]) for t in wins)
    gl = -sum(float(t["net_pnl"]) for t in losses)
    pf = (gp / gl) if gl > 1e-12 else (1e9 if gp > 0 else 0.0)
    ret = equity / float(start_equity) - 1.0 if start_equity > 0 else None

    return {
        "formal_status": "ok",
        "protocol": "priority_single_slot",
        "timeframe_minutes": tf,
        "start_equity": start_equity,
        "ending_equity": equity,
        "return_fraction": ret,
        "trades": len(trades),
        "profit_factor": pf if pf < 1e8 else None,
        "max_drawdown_fraction": max_dd,
        "permanent_account_state": permanent,
        "entries_by_leg": entries_by_leg,
        "peak_equity": peak,
    }


def run_majors_combo_research(
    data_dir: Path,
    *,
    start_equity: float = DEFAULT_START_EQUITY_USDT,
) -> dict[str, Any]:
    cat = combo_legs_catalog()
    primary = cat["h1_high_vol_donchian_short"]

    # Baseline single
    base_rep = replay_majors_account(
        data_dir, config=primary.config, start_equity=start_equity
    )
    baseline = _summary_from_replay(base_rep)
    baseline["name"] = primary.name

    experiments: list[dict[str, Any]] = []

    # --- independent equal weight sets ---
    indep_sets = [
        ["h1_high_vol_donchian_short", "h1_failed_breakout_short"],
        ["h1_high_vol_donchian_short", "h1_failed_breakdown_long"],
        [
            "h1_high_vol_donchian_short",
            "h1_failed_breakout_short",
            "h1_failed_breakdown_long",
        ],
        ["h1_high_vol_donchian_short", "h4_weekly_mom_short"],
        ["h1_high_vol_donchian_short", "h4_high_vol_donchian_short"],
        ["h1_high_vol_donchian_short", "m15_failed_breakout_short"],
        [
            "h1_high_vol_donchian_short",
            "h4_weekly_mom_short",
            "m15_failed_breakout_short",
        ],
    ]
    for names in indep_sets:
        legs = [cat[n] for n in names]
        exp = _independent_equal_weight(data_dir, legs, start_equity=start_equity)
        exp["leg_names"] = names
        experiments.append(exp)

    # --- priority single slot same TF ---
    priority_sets = [
        ["h1_high_vol_donchian_short", "h1_failed_breakout_short"],
        ["h1_high_vol_donchian_short", "h1_failed_breakdown_long"],
        [
            "h1_high_vol_donchian_short",
            "h1_failed_breakout_short",
            "h1_failed_breakdown_long",
        ],
        # reverse priority (secondary first) — stress
        ["h1_failed_breakout_short", "h1_high_vol_donchian_short"],
    ]
    for names in priority_sets:
        ordered = [
            ComboLeg(name=n, config=cat[n].config, role=cat[n].role) for n in names
        ]
        port = _replay_priority_with_dd(
            data_dir, ordered, start_equity=start_equity
        )
        prim_ret = float(baseline.get("return_fraction") or 0)
        port_ret = port.get("return_fraction")
        experiments.append(
            {
                "protocol": "priority_single_slot",
                "formal_status": port.get("formal_status"),
                "leg_names": names,
                "priority_order": names,
                "portfolio": {
                    **{k: v for k, v in port.items() if k != "formal_status"},
                    "beats_primary_return": (
                        port_ret is not None and float(port_ret) > prim_ret + 1e-12
                    ),
                    "primary_return": prim_ret,
                    "return_edge_vs_primary": (
                        float(port_ret) - prim_ret if port_ret is not None else None
                    ),
                },
            }
        )

    # Decision
    beats = []
    for e in experiments:
        port = e.get("portfolio") or {}
        if e.get("formal_status") == "ok" and port.get("beats_primary_return"):
            beats.append(
                {
                    "protocol": e.get("protocol"),
                    "leg_names": e.get("leg_names"),
                    "return_fraction": port.get("return_fraction"),
                    "edge_vs_primary": port.get("return_edge_vs_primary"),
                }
            )

    decision = (
        "combo_can_beat_primary_in_sample"
        if beats
        else "combo_does_not_beat_primary"
    )
    # Conservative operator decision: only promote if priority protocol beats
    # with more trades diversity AND not just independent diluted average of weaker legs
    priority_beats = [b for b in beats if b["protocol"] == "priority_single_slot"]
    operator = (
        "do_not_replace_primary_with_combo"
        if not priority_beats
        else "investigate_priority_combo_further_with_oos"
    )

    return {
        "report_type": "majors_combo_research_v1",
        "as_of": _utc_now(),
        "formal_status": "ok",
        "start_equity": start_equity,
        "baseline_primary": baseline,
        "experiments": experiments,
        "combos_beating_primary_full_sample": beats,
        "decision": decision,
        "operator_action": operator,
        "places_exchange_orders": False,
        "live_allowed": False,
        "notes": [
            "Independent equal-weight is capital-split model (not shared path).",
            "Priority single-slot is shared path, one position, same timeframe.",
            "Full-sample only; any promote needs multiwindow OOS next.",
            "Not paper admission for combo sleeves.",
        ],
    }


def write_combo_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
