"""Local paper runtime for production-bound BTC/ETH majors sleeve.

Never places OKX demo/live orders. Uses the same frozen rule as
majors_account_replay for signal/exit logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from market import FeatureBar, load_market
from prod.graduation import evaluate_local_paper_graduation
from prod.majors_account_replay import (
    _one_way_cost_rate,
    _size_position,
    resolve_entry_signal,
)
from prod.majors_contract import (
    MajorsSleeveConfig,
    STRATEGY_ID,
    TRACK,
    resolve_sleeve_config,
)
from prod.policy import (
    DEFAULT_START_EQUITY_USDT,
    annotate_local_paper_cycle,
    default_pipeline_places_exchange_orders,
)
from prod.registry import DEFAULT_REGISTRY_PATH, get_entry, is_paper_allowed


DEFAULT_STATE_PATH = Path("reports/prod/majors_paper_state.json")
DEFAULT_CYCLE_PATH = Path("reports/prod/majors_paper_cycle.json")
DEFAULT_DATA_DIR = Path("data")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_state(path: Path, config: MajorsSleeveConfig | None = None) -> dict[str, Any]:
    cfg = config or MajorsSleeveConfig()
    if not path.exists():
        return {
            "state_type": "majors_paper_state",
            "strategy_id": STRATEGY_ID,
            "track": TRACK,
            "mode": "local_paper",
            "equity": float(cfg.start_equity),
            "peak_equity": float(cfg.start_equity),
            "open_position": None,
            "closed_trades": [],
            "last_cycle_at": None,
            "halt_reason": None,
            "places_exchange_orders": default_pipeline_places_exchange_orders(),
            "live_allowed": False,
            "completed_cycle_count": 0,
            "symbols": list(cfg.symbols),
            "config_fingerprint": cfg.fingerprint(),
            "track_class": "production_bound",
            "demo_live_graduation_eligible": True,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _manage_open(
    state: dict[str, Any],
    market: dict[str, list[FeatureBar]],
    config: MajorsSleeveConfig,
) -> dict[str, Any] | None:
    open_pos = state.get("open_position")
    if not open_pos:
        return None
    sym = open_pos["symbol"]
    bars = market.get(sym) or []
    if not bars:
        return {"action": "hold_open_missing_bars", "symbol": sym}
    bar = bars[-1]
    cost = _one_way_cost_rate(config)
    stop = float(open_pos["stop"])
    tp = float(open_pos["take_profit"])
    trail = float(open_pos.get("trail", stop))
    entry = float(open_pos["entry_price"])
    qty = float(open_pos["qty"])
    entry_idx = int(open_pos.get("entry_idx", 0))
    direction = open_pos.get("direction", "long")
    dir_sign = -1 if direction == "short" else 1
    held = max(0, len(bars) - 1 - entry_idx) if entry_idx < len(bars) else int(
        open_pos.get("held_bars", 0)
    ) + 1

    exit_price = None
    exit_reason = None
    if dir_sign >= 0:
        if bar.low <= stop:
            exit_price = stop
            exit_reason = "stop"
        elif bar.high >= tp:
            exit_price = tp
            exit_reason = "take_profit"
        else:
            new_trail = bar.close - config.trailing_atr * bar.atr
            if new_trail > trail:
                trail = new_trail
                stop = max(stop, new_trail)
                open_pos["trail"] = trail
                open_pos["stop"] = stop
                state["open_position"] = open_pos
            if held >= config.max_hold_bars:
                exit_price = bar.close
                exit_reason = "time_stop"
    else:
        if bar.high >= stop:
            exit_price = stop
            exit_reason = "stop"
        elif bar.low <= tp:
            exit_price = tp
            exit_reason = "take_profit"
        else:
            new_trail = bar.close + config.trailing_atr * bar.atr
            if new_trail < trail:
                trail = new_trail
                stop = min(stop, new_trail)
                open_pos["trail"] = trail
                open_pos["stop"] = stop
                state["open_position"] = open_pos
            if held >= config.max_hold_bars:
                exit_price = bar.close
                exit_reason = "time_stop"

    if exit_price is None:
        open_pos["held_bars"] = held
        state["open_position"] = open_pos
        return {"action": "still_open", "symbol": sym, "held_bars": held}

    if dir_sign >= 0:
        fill = exit_price * (1.0 - cost)
        pnl = (fill - entry) * qty
    else:
        fill = exit_price * (1.0 + cost)
        pnl = (entry - fill) * qty
    equity_before = float(open_pos.get("equity_before", state["equity"]))
    equity_after = max(0.0, float(state["equity"]) + pnl)
    closed = {
        "symbol": sym,
        "direction": "long" if dir_sign >= 0 else "short",
        "entry_price": entry,
        "exit_price": fill,
        "net_pnl": pnl,
        "exit_reason": exit_reason,
        "equity_before": equity_before,
        "equity_after": equity_after,
        "closed_at": _utc_now(),
    }
    state["closed_trades"].append(closed)
    state["equity"] = equity_after
    state["peak_equity"] = max(float(state.get("peak_equity", equity_after)), equity_after)
    state["open_position"] = None
    if equity_after <= float(config.ruin_equity):
        state["halt_reason"] = "ruined"
    else:
        peak = float(state["peak_equity"])
        if peak > 0 and (1.0 - equity_after / peak) >= float(config.peak_drawdown_halt):
            state["halt_reason"] = "peak_drawdown_halt"
    return {"action": "closed", "trade": closed}


def _try_open(
    state: dict[str, Any],
    market: dict[str, list[FeatureBar]],
    config: MajorsSleeveConfig,
    funding_filter: str = "none",
) -> dict[str, Any]:
    if state.get("open_position") or state.get("halt_reason"):
        return {"action": "skip_entry_blocked"}
    cost = _one_way_cost_rate(config)
    equity = float(state["equity"])
    # Build index at last common ts
    if not market:
        return {"action": "no_new_entry"}
    last_ts = min(bars[-1].ts for bars in market.values() if bars)
    index = {sym: {b.ts: i for i, b in enumerate(bars)} for sym, bars in market.items()}
    resolved = resolve_entry_signal(
        market,
        index,
        last_ts,
        config,
        tuple(config.symbols),
        funding_filter=funding_filter,
    )
    if resolved is None:
        return {"action": "no_new_entry"}
    sym, direction = resolved
    bars = market[sym]
    i = index[sym][last_ts]
    bar = bars[i]
    if direction > 0:
        raw_entry = bar.close * (1.0 + cost)
        stop = raw_entry - config.stop_atr * bar.atr
        tp = raw_entry + config.take_profit_atr * bar.atr
        dir_label = "long"
    else:
        raw_entry = bar.close * (1.0 - cost)
        stop = raw_entry + config.stop_atr * bar.atr
        tp = raw_entry - config.take_profit_atr * bar.atr
        dir_label = "short"
    sized = _size_position(equity, raw_entry, stop, config)
    if sized is None:
        return {
            "action": "skip_proposal",
            "symbol": sym,
            "reason": "size_or_min_notional_blocked",
        }
    qty, notional, margin = sized
    pos = {
        "symbol": sym,
        "direction": dir_label,
        "entry_price": raw_entry,
        "qty": qty,
        "notional": notional,
        "margin": margin,
        "stop": stop,
        "take_profit": tp,
        "trail": stop,
        "entry_idx": i,
        "held_bars": 0,
        "equity_before": equity,
        "opened_at": _utc_now(),
        "bar_time": bar.time,
    }
    state["open_position"] = pos
    return {"action": "opened", "position": pos}


def run_majors_paper_cycle(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    state_path: Path = DEFAULT_STATE_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cycle_path: Path = DEFAULT_CYCLE_PATH,
    force: bool = False,
    config: MajorsSleeveConfig | None = None,
    strategy_id: str | None = None,
    funding_filter: str = "none",
) -> dict[str, Any]:
    sid = strategy_id or (config.strategy_id if config else STRATEGY_ID)
    if config is None:
        config = resolve_sleeve_config(sid) or MajorsSleeveConfig()
    cfg = config
    if not is_paper_allowed(sid, registry_path) and not force:
        report = {
            "report_type": "majors_paper_cycle",
            "formal_status": "blocked_not_in_paper_prep_registry",
            "strategy_id": sid,
            "as_of": _utc_now(),
            "hint": "Admit strategy to paper_prep registry first",
            "places_exchange_orders": False,
            "live_allowed": False,
        }
        cycle_path.parent.mkdir(parents=True, exist_ok=True)
        cycle_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    entry = get_entry(sid, registry_path) or {}
    state = load_state(state_path, cfg)
    state["strategy_id"] = sid
    if state.get("halt_reason"):
        grad = evaluate_local_paper_graduation(
            state,
            registry_entry=entry or None,
            symbols=list(cfg.symbols),
        )
        report = {
            "report_type": "majors_paper_cycle",
            "formal_status": "halted",
            "halt_reason": state["halt_reason"],
            "equity": state.get("equity"),
            "as_of": _utc_now(),
            "mode": "local_paper",
            "live_allowed": False,
            "places_exchange_orders": False,
            "local_graduation": grad.to_dict(),
            "track_class": "production_bound",
            "strategy_id": sid,
        }
        cycle_path.parent.mkdir(parents=True, exist_ok=True)
        cycle_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    market = load_market(
        data_dir,
        cfg.timeframe_minutes,
        include_funding=(funding_filter != "none"),
        symbols=set(cfg.symbols),
    )
    if not market:
        report = {
            "report_type": "majors_paper_cycle",
            "formal_status": "data_missing",
            "strategy_id": sid,
            "as_of": _utc_now(),
            "places_exchange_orders": False,
            "live_allowed": False,
        }
        cycle_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    actions: list[dict[str, Any]] = []
    open_result = _manage_open(state, market, cfg)
    if open_result:
        actions.append(open_result)
    if state.get("open_position") is None and not state.get("halt_reason"):
        actions.append(_try_open(state, market, cfg, funding_filter=funding_filter))

    state["last_cycle_at"] = _utc_now()
    state["config_fingerprint"] = cfg.fingerprint()
    state["registry_status"] = entry.get("status")
    state["mode"] = "local_paper"
    state["places_exchange_orders"] = False
    state["live_allowed"] = False
    state["completed_cycle_count"] = int(state.get("completed_cycle_count") or 0) + 1
    state["symbols"] = list(cfg.symbols)
    policy_block = annotate_local_paper_cycle(
        symbols=cfg.symbols,
        start_equity=float(state.get("equity", DEFAULT_START_EQUITY_USDT)),
    )
    state["track_class"] = policy_block["track_class"]
    state["demo_live_graduation_eligible"] = policy_block["demo_live_graduation_eligible"]
    graduation = evaluate_local_paper_graduation(
        state,
        registry_entry=entry or None,
        symbols=list(cfg.symbols),
    )
    state["local_graduation_decision"] = graduation.decision
    state["local_graduation_graduated"] = graduation.graduated_local
    save_state(state, state_path)

    latest_times = {
        sym: (bars[-1].time if bars else None) for sym, bars in market.items()
    }
    report = {
        "report_type": "majors_paper_cycle",
        "formal_status": "ok",
        "strategy_id": sid,
        "config_fingerprint": cfg.fingerprint(),
        "as_of": _utc_now(),
        "data_through": latest_times,
        "equity": state["equity"],
        "peak_equity": state["peak_equity"],
        "open_position": state.get("open_position"),
        "closed_trade_count": len(state.get("closed_trades") or []),
        "completed_cycle_count": state["completed_cycle_count"],
        "actions": actions,
        "mode": "local_paper",
        "live_allowed": False,
        "places_exchange_orders": False,
        "exchange_orders_submitted": 0,
        "track_class": policy_block["track_class"],
        "demo_live_graduation_eligible": policy_block["demo_live_graduation_eligible"],
        "local_graduation": graduation.to_dict(),
        "operator_policy": policy_block["operator_policy"],
        "universe_validation": policy_block["universe_validation"],
        "start_equity_validation": policy_block["start_equity_validation"],
        "notes": (
            "Production-bound BTC/ETH local paper only. "
            "No exchange orders. Not a demo/live authorization."
        ),
    }
    cycle_path.parent.mkdir(parents=True, exist_ok=True)
    cycle_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
