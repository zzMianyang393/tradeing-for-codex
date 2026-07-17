"""10U high-risk paper-prep runtime.

Does NOT wait for prospective sealed evaluation.
Requires an entry in reports/prod/paper_prep_registry.json with status paper_prep.

Default mode is local paper ledger (no exchange). Optional --okx-sandbox only
prints/submits after explicit confirmation flags — live is never enabled here.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from prod.registry import DEFAULT_REGISTRY_PATH, get_entry, is_paper_allowed
from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig, STRATEGY_ID
from ten_u_event_trend_data_v1 import HOUR_MS, parse_utc
from ten_u_event_trend_formation_v1 import (
    InstrumentSpec,
    load_bars,
    load_funding,
    simulate_trade,
)
from ten_u_event_trend_screen_v2 import (
    _execution_config,
    build_v2_proposals,
    find_persistence_confirmations,
    next_entry_available_at,
)


DEFAULT_STATE_PATH = Path("reports/prod/ten_u_paper_state.json")
DEFAULT_CYCLE_PATH = Path("reports/prod/ten_u_paper_cycle.json")
DEFAULT_DATA_DIR = Path("data/event_trend_v1")
DEFAULT_MANIFEST = Path("data/event_trend_v1/hourly_dataset_manifest_v1.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "state_type": "ten_u_paper_state",
            "strategy_id": STRATEGY_ID,
            "mode": "local_paper",
            "equity": 10.0,
            "peak_equity": 10.0,
            "open_position": None,
            "closed_trades": [],
            "last_cycle_at": None,
            "halt_reason": None,
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_universe(data_dir: Path, manifest_path: Path, config: PersistentEventTrendConfig):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bars_by_symbol: dict[str, list] = {}
    funding_by_symbol: dict[str, list] = {}
    specs: dict[str, InstrumentSpec] = {}
    for symbol in config.symbols:
        item = manifest["symbols"][symbol]
        path = Path(item["path"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"dataset fingerprint drift for {symbol}")
        bars_by_symbol[symbol] = load_bars(path)
        funding_by_symbol[symbol] = load_funding(data_dir / f"{symbol}_funding.csv")
        inst = item["instrument"]
        specs[symbol] = InstrumentSpec(
            symbol,
            float(inst["ctVal"]),
            float(inst["lotSz"]),
            float(inst["minSz"]),
        )
    return bars_by_symbol, funding_by_symbol, specs


def _latest_completed_ts(bars_by_symbol: dict[str, list]) -> int:
    return max(bars[-1].ts for bars in bars_by_symbol.values() if bars)


def _manage_open_position(
    state: dict[str, Any],
    bars_by_symbol: dict[str, list],
    funding_by_symbol: dict[str, list],
    specs: dict[str, InstrumentSpec],
    config: PersistentEventTrendConfig,
    end_ms: int,
) -> dict[str, Any] | None:
    open_pos = state.get("open_position")
    if not open_pos:
        return None
    from ten_u_event_trend_formation_v1 import EntryProposal

    proposal = EntryProposal(
        symbol=open_pos["symbol"],
        direction=open_pos["direction"],
        ignition_ts=int(open_pos["ignition_ts"]),
        entry_ts=int(open_pos["entry_ts"]),
        structural_invalidation=float(open_pos["structural_invalidation"]),
        atr_1h=float(open_pos["atr_1h"]),
        score=float(open_pos.get("score", 0.0)),
    )
    trade = simulate_trade(
        proposal,
        bars_by_symbol[proposal.symbol],
        funding_by_symbol[proposal.symbol],
        specs[proposal.symbol],
        _execution_config(config),
        float(open_pos["equity_before"]),
        end_ms,
    )
    if not trade.get("accepted"):
        return {"action": "hold_open_unresolved", "detail": trade}
    # formation_boundary means the replay hit the data end while still open.
    if trade.get("exit_reason") == "formation_boundary":
        return {
            "action": "still_open",
            "mark": {k: trade[k] for k in trade if k != "marks"},
        }
    equity_before = float(open_pos["equity_before"])
    equity_after = max(0.0, equity_before + float(trade["net_pnl"]))
    closed = {
        **{k: trade[k] for k in trade if k != "marks"},
        "equity_before": equity_before,
        "equity_after": equity_after,
        "closed_at": _utc_now(),
    }
    state["closed_trades"].append(closed)
    state["equity"] = equity_after
    state["peak_equity"] = max(float(state.get("peak_equity", equity_after)), equity_after)
    state["open_position"] = None
    state["available_after_ts"] = next_entry_available_at(closed)
    if equity_after <= float(config.ruin_equity):
        state["halt_reason"] = "ruined"
    return {"action": "closed", "trade": closed}


def _find_new_entries(
    bars_by_symbol: dict[str, list],
    config: PersistentEventTrendConfig,
    lookback_start_ms: int,
    end_ms: int,
) -> list:
    proposals = []
    for symbol, bars in bars_by_symbol.items():
        conf = find_persistence_confirmations(
            symbol, bars, config, lookback_start_ms, end_ms
        )
        props = build_v2_proposals(
            symbol, bars, conf, config, end_ms, allow_entry_at_end=True
        )
        proposals.extend(props)
    proposals.sort(key=lambda p: (p.entry_ts, -p.score, p.symbol))
    return proposals


def run_paper_cycle(
    *,
    data_dir: Path = DEFAULT_DATA_DIR,
    manifest_path: Path = DEFAULT_MANIFEST,
    state_path: Path = DEFAULT_STATE_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    cycle_path: Path = DEFAULT_CYCLE_PATH,
    lookback_days: int = 120,
    force: bool = False,
) -> dict[str, Any]:
    config = PersistentEventTrendConfig()
    if not is_paper_allowed(STRATEGY_ID, registry_path) and not force:
        report = {
            "report_type": "ten_u_paper_cycle",
            "formal_status": "blocked_not_in_paper_prep_registry",
            "strategy_id": STRATEGY_ID,
            "as_of": _utc_now(),
            "hint": "Run: python -m prod.cli admit-ten-u --accept-concentration-risk",
        }
        cycle_path.parent.mkdir(parents=True, exist_ok=True)
        cycle_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    entry = get_entry(STRATEGY_ID, registry_path) or {}
    state = load_state(state_path)
    if state.get("halt_reason"):
        report = {
            "report_type": "ten_u_paper_cycle",
            "formal_status": "halted",
            "halt_reason": state["halt_reason"],
            "equity": state.get("equity"),
            "as_of": _utc_now(),
        }
        cycle_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    bars_by_symbol, funding_by_symbol, specs = _load_universe(
        data_dir, manifest_path, config
    )
    latest_ts = _latest_completed_ts(bars_by_symbol)
    # exclusive end = last bar open + 1h so the last completed hour is usable
    end_ms = latest_ts + HOUR_MS
    lookback_start_ms = end_ms - lookback_days * 24 * HOUR_MS

    actions: list[dict[str, Any]] = []
    open_result = _manage_open_position(
        state, bars_by_symbol, funding_by_symbol, specs, config, end_ms
    )
    if open_result:
        actions.append(open_result)

    opened = None
    if state.get("open_position") is None and not state.get("halt_reason"):
        available_after = int(state.get("available_after_ts") or 0)
        proposals = _find_new_entries(
            bars_by_symbol, config, lookback_start_ms, end_ms
        )
        # Only act on entries that become executable at/after last bar close
        # (entry_ts == latest_ts + 1h means known at latest completed close)
        actionable = [
            p
            for p in proposals
            if p.entry_ts >= latest_ts
            and p.entry_ts <= end_ms
            and p.entry_ts >= available_after
        ]
        if actionable:
            chosen = sorted(actionable, key=lambda p: (-p.score, p.symbol))[0]
            sim = simulate_trade(
                chosen,
                bars_by_symbol[chosen.symbol],
                funding_by_symbol[chosen.symbol],
                specs[chosen.symbol],
                _execution_config(config),
                float(state["equity"]),
                end_ms,
            )
            if sim.get("accepted"):
                state["open_position"] = {
                    "symbol": chosen.symbol,
                    "direction": chosen.direction,
                    "ignition_ts": chosen.ignition_ts,
                    "entry_ts": chosen.entry_ts,
                    "structural_invalidation": chosen.structural_invalidation,
                    "atr_1h": chosen.atr_1h,
                    "score": chosen.score,
                    "equity_before": float(state["equity"]),
                    "opened_at": _utc_now(),
                    "entry_price": sim.get("entry_price"),
                    "notional": sim.get("notional"),
                }
                opened = state["open_position"]
                actions.append({"action": "opened", "position": opened})
            else:
                actions.append(
                    {
                        "action": "skip_proposal",
                        "symbol": chosen.symbol,
                        "entry_ts": chosen.entry_ts,
                        "reason": sim.get("reason") or sim.get("skip_reason") or "rejected",
                        "detail": {k: sim[k] for k in sim if k != "marks"},
                    }
                )
        else:
            actions.append(
                {
                    "action": "no_new_entry",
                    "proposals_in_lookback": len(proposals),
                    "latest_bar_ts": _iso(latest_ts),
                }
            )

    state["last_cycle_at"] = _utc_now()
    state["config_fingerprint"] = config.fingerprint()
    state["registry_status"] = entry.get("status")
    save_state(state, state_path)

    report = {
        "report_type": "ten_u_paper_cycle",
        "formal_status": "ok",
        "strategy_id": STRATEGY_ID,
        "config_fingerprint": config.fingerprint(),
        "as_of": _utc_now(),
        "data_through": _iso(latest_ts),
        "equity": state["equity"],
        "peak_equity": state["peak_equity"],
        "open_position": state.get("open_position"),
        "closed_trade_count": len(state.get("closed_trades") or []),
        "actions": actions,
        "mode": "local_paper",
        "live_allowed": False,
        "exchange_orders_submitted": 0,
        "notes": (
            "Local paper sleeve only. OKX auto-submit is not enabled in this cycle. "
            "Prospective sealed wait is not required."
        ),
    }
    cycle_path.parent.mkdir(parents=True, exist_ok=True)
    cycle_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
