"""Sealed prospective evaluator for the 10U persistent event-trend v2."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from ten_u_event_trend_contract_v1 import _jsonable, _utc
from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig
from ten_u_event_trend_data_v1 import HOUR_MS, parse_utc
from ten_u_event_trend_formation_v1 import (
    EntryProposal,
    FundingPoint,
    HourBar,
    InstrumentSpec,
    load_bars,
    load_funding,
)
from ten_u_event_trend_prospective_v2 import (
    ProspectiveMaturityGateV2,
    build_prospective_registration,
    validate_ledger,
)
from ten_u_event_trend_refresh_v2 import validate_refresh_audit
from ten_u_event_trend_screen_v2 import replay_proposals


@dataclass(frozen=True)
class ProspectiveEvaluationSpecV2:
    version: str = "v1.1.0"
    completed_outcome_horizon_hours: int = 48
    signal_selection: str = "ledger_records_with_full_48h_outcome_only"
    same_timestamp_arbitration: str = "score_desc_then_symbol_asc"
    capital_model: str = "single_isolated_10u_sleeve"
    stop_sweep_metric: str = "hard_stop_then_return_to_entry_before_original_48h_horizon"
    winner_capture_metric: str = "gross_price_move_retained_from_mfe_excluding_funding"
    marked_equity_metric: str = "executable_liquidation_equity_including_exit_fee_and_slippage"
    result_policy: str = "first_mature_evaluation_is_binding"
    intrabar_stop_reentry_policy: str = "next_completed_hour_open_only"
    hard_stop_gap_fill_policy: str = "worse_of_stop_or_hour_open_then_slippage"

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_evaluator_registration(root: Path | None = None) -> dict[str, Any]:
    root = root or Path(__file__).resolve().parent
    config = PersistentEventTrendConfig()
    gate = ProspectiveMaturityGateV2()
    spec = ProspectiveEvaluationSpecV2()
    source_files = (
        "ten_u_event_trend_evaluation_v2.py",
        "ten_u_event_trend_screen_v2.py",
        "ten_u_event_trend_formation_v1.py",
        "ten_u_event_trend_prospective_v2.py",
        "ten_u_event_trend_refresh_v2.py",
    )
    return {
        "registration_version": "v1.1.0",
        "formal_status": "frozen_before_prospective_outcomes",
        "strategy_id": config.strategy_id,
        "config_fingerprint": config.fingerprint(),
        "gate_fingerprint": gate.fingerprint(),
        "evaluation_spec": spec.to_dict(),
        "evaluation_spec_fingerprint": spec.fingerprint(),
        "source_sha256": {name: _file_hash(root / name) for name in source_files},
        "outcomes_accessed_at_registration": False,
    }


def assess_maturity(
    registration: dict[str, Any], ledger: dict[str, Any], as_of: str
) -> dict[str, Any]:
    validate_ledger(ledger)
    gate = ProspectiveMaturityGateV2()
    spec = ProspectiveEvaluationSpecV2()
    now = _utc(as_of)
    earliest = _utc(registration["earliest_evaluation"])
    cutoff_text = ledger.get("available_through", registration["prospective_start"])
    cutoff = _utc(cutoff_text)
    cutoff_ms = int(cutoff.timestamp() * 1000)
    outcome_horizon_ms = spec.completed_outcome_horizon_hours * HOUR_MS
    eligible = [
        record
        for record in ledger["records"]
        if record["entry_ts"] + outcome_horizon_ms <= cutoff_ms
    ]
    reasons: list[str] = []
    if now < earliest:
        reasons.append("calendar_days_below_minimum")
    if cutoff < earliest:
        reasons.append("observation_coverage_below_minimum")
    if len(eligible) < gate.minimum_trades:
        reasons.append("completed_signal_outcomes_below_minimum")
    return {
        "formal_status": "mature_for_sealed_outcome_access" if not reasons else "prospective_not_mature",
        "as_of": as_of,
        "available_through": cutoff_text,
        "eligible_completed_signal_records": len(eligible),
        "total_signal_records": len(ledger["records"]),
        "reasons": reasons,
        "eligible_records": eligible,
        "outcomes_may_be_accessed": not reasons,
    }


def _load_and_replay(
    data_dir: Path,
    manifest_path: Path,
    eligible_records: list[dict[str, Any]],
    cutoff_ms: int,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("coverage_status") != "PASS":
        raise ValueError("prospective hourly coverage is not complete")
    if parse_utc(manifest["requested_end"].replace("+00:00", "Z")) < cutoff_ms:
        raise ValueError("prospective manifest ends before the sealed cutoff")
    config = PersistentEventTrendConfig()
    bars_by_symbol: dict[str, list[HourBar]] = {}
    funding_by_symbol: dict[str, list[FundingPoint]] = {}
    specs: dict[str, InstrumentSpec] = {}
    funding_coverage: dict[str, Any] = {}
    start_ms = parse_utc("2026-07-16T00:00:00Z")
    for symbol in config.symbols:
        item = manifest["symbols"][symbol]
        candle_path = Path(item["path"])
        if _file_hash(candle_path) != item["sha256"]:
            raise ValueError(f"prospective candle fingerprint drift: {symbol}")
        bars_by_symbol[symbol] = load_bars(candle_path)
        funding_item = item.get("funding")
        if not funding_item or funding_item.get("validation", {}).get("status") != "PASS":
            raise ValueError(f"funding is not bound into the working manifest: {symbol}")
        funding_path = Path(funding_item["path"])
        if _file_hash(funding_path) != funding_item["sha256"]:
            raise ValueError(f"prospective funding fingerprint drift: {symbol}")
        funding = load_funding(funding_path)
        relevant = [point for point in funding if start_ms <= point.ts < cutoff_ms]
        max_gap = max(
            ((right.ts - left.ts) / HOUR_MS for left, right in zip(relevant, relevant[1:])),
            default=math.inf,
        )
        boundary_covered = bool(
            relevant
            and relevant[0].ts <= start_ms + 8 * HOUR_MS
            and relevant[-1].ts >= cutoff_ms - 8 * HOUR_MS
        )
        funding_coverage[symbol] = {
            "points": len(relevant),
            "maximum_gap_hours": max_gap,
            "boundary_covered": boundary_covered,
            "sha256": _file_hash(funding_path),
            "status": "PASS" if max_gap <= 8 and boundary_covered else "FAIL",
        }
        funding_by_symbol[symbol] = funding
        instrument = item["instrument"]
        specs[symbol] = InstrumentSpec(
            symbol=symbol,
            contract_value_base=float(instrument["ctVal"]),
            lot_size_contracts=float(instrument["lotSz"]),
            minimum_contracts=float(instrument["minSz"]),
        )
    if any(item["status"] != "PASS" for item in funding_coverage.values()):
        raise ValueError("complete actual funding history is required before evaluation")
    proposals = [
        EntryProposal(
            symbol=record["symbol"],
            direction=record["direction"],
            ignition_ts=record["ignition_ts"],
            entry_ts=record["entry_ts"],
            structural_invalidation=float(record["structural_invalidation"]),
            atr_1h=float(record["atr_1h"]),
            score=float(record["score"]),
        )
        for record in eligible_records
    ]
    replay = replay_proposals(
        proposals, bars_by_symbol, funding_by_symbol, specs, config, cutoff_ms
    )
    positive = [trade["net_pnl"] for trade in replay["trades_detail"] if trade["net_pnl"] > 0]
    replay["top_winner_gross_profit_contribution"] = (
        max(positive) / sum(positive) if positive else 0.0
    )
    replay["distinct_traded_symbols"] = sum(
        count > 0 for count in replay["trades_by_symbol"].values()
    )
    replay["funding_coverage"] = funding_coverage
    replay["dataset_manifest_sha256"] = _file_hash(manifest_path)
    return replay


def evaluate_replay(replay: dict[str, Any]) -> tuple[str, list[str]]:
    gate = ProspectiveMaturityGateV2()
    if replay["trades"] < gate.minimum_trades:
        return "prospective_insufficient_executed_trades", ["executed_trades_below_minimum"]
    reasons: list[str] = []
    checks = (
        (replay["wins"] < gate.minimum_wins, "wins_below_minimum"),
        (
            replay["distinct_traded_symbols"] < gate.minimum_distinct_traded_symbols,
            "distinct_symbols_below_minimum",
        ),
        (replay["profit_factor"] < float(gate.minimum_profit_factor), "profit_factor_below_minimum"),
        (replay["ending_equity"] < float(gate.minimum_ending_equity), "ending_equity_below_minimum"),
        (
            replay["max_drawdown_fraction"] > float(gate.maximum_drawdown_fraction),
            "drawdown_above_maximum",
        ),
        (
            replay["peak_profit_retention"] < float(gate.minimum_peak_profit_retention),
            "peak_profit_retention_below_minimum",
        ),
        (
            replay["stopped_then_recovered_fraction"]
            > float(gate.maximum_stopped_then_recovered_fraction),
            "stopped_then_recovered_above_maximum",
        ),
        (
            replay["median_winner_capture"] < float(gate.minimum_median_winner_capture),
            "median_winner_capture_below_minimum",
        ),
        (
            replay["top_winner_gross_profit_contribution"]
            > float(gate.maximum_top_winner_gross_profit_contribution),
            "top_winner_contribution_above_maximum",
        ),
    )
    reasons.extend(reason for failed, reason in checks if failed)
    return ("prospective_pass" if not reasons else "prospective_fail", reasons)


OutcomeLoader = Callable[[Path, Path, list[dict[str, Any]], int], dict[str, Any]]


def run_sealed_evaluation(
    registration_path: Path,
    evaluator_registration_path: Path,
    baseline_manifest_path: Path,
    ledger_path: Path,
    refresh_audit_path: Path,
    data_dir: Path,
    working_manifest_path: Path,
    as_of: str,
    report_path: Path | None = None,
    *,
    outcome_loader: OutcomeLoader = _load_and_replay,
) -> dict[str, Any]:
    registration = json.loads(registration_path.read_text(encoding="utf-8"))
    if registration != build_prospective_registration(baseline_manifest_path):
        raise ValueError("prospective registration drift")
    evaluator_registration = json.loads(
        evaluator_registration_path.read_text(encoding="utf-8")
    )
    if evaluator_registration != build_evaluator_registration():
        raise ValueError("sealed evaluator source drift")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    validate_ledger(ledger)
    audit = json.loads(refresh_audit_path.read_text(encoding="utf-8"))
    validate_refresh_audit(audit)
    if not audit["records"] or audit["records"][-1]["ledger_head_hash_after"] != ledger["head_hash"]:
        raise ValueError("refresh audit does not bind the current signal ledger")
    maturity = assess_maturity(registration, ledger, as_of)
    if not maturity["outcomes_may_be_accessed"]:
        report = {
            **{key: value for key, value in maturity.items() if key != "eligible_records"},
            "outcomes_accessed": False,
            "decision": "continue_signal_only_observation",
        }
        if report_path:
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    cutoff_ms = parse_utc(maturity["available_through"])
    replay = outcome_loader(
        data_dir, working_manifest_path, maturity["eligible_records"], cutoff_ms
    )
    status, reasons = evaluate_replay(replay)
    report = {
        **{key: value for key, value in maturity.items() if key != "eligible_records"},
        "formal_status": status,
        "gate_reasons": reasons,
        "outcomes_accessed": True,
        "evaluation_spec_fingerprint": ProspectiveEvaluationSpecV2().fingerprint(),
        "result": replay,
        "decision": (
            "promote_to_paper_only" if status == "prospective_pass" else
            "continue_until_executed_trade_minimum" if status == "prospective_insufficient_executed_trades" else
            "reject_v2_without_parameter_rescue"
        ),
    }
    if report_path:
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", help="Explicit UTC Z timestamp")
    parser.add_argument("--print-registration", action="store_true")
    parser.add_argument("--registration", type=Path, default=Path("reports/ten_u_event_trend_prospective_registration_v2.json"))
    parser.add_argument("--evaluator-registration", type=Path, default=Path("reports/ten_u_event_trend_evaluator_registration_v2.json"))
    parser.add_argument("--baseline-manifest", type=Path, default=Path("reports/ten_u_event_trend_baseline_dataset_manifest_v2.json"))
    parser.add_argument("--ledger", type=Path, default=Path("reports/ten_u_event_trend_prospective_ledger_v2.json"))
    parser.add_argument("--refresh-audit", type=Path, default=Path("reports/ten_u_event_trend_prospective_refresh_audit_v2.json"))
    parser.add_argument("--data", type=Path, default=Path("data/event_trend_v1"))
    parser.add_argument("--manifest", type=Path, default=Path("data/event_trend_v1/hourly_dataset_manifest_v1.json"))
    parser.add_argument("--report", type=Path, default=Path("reports/ten_u_event_trend_prospective_evaluation_v2.json"))
    args = parser.parse_args()
    if args.print_registration:
        print(json.dumps(build_evaluator_registration(), indent=2))
        return 0
    if not args.as_of:
        parser.error("--as-of is required unless --print-registration is used")
    report = run_sealed_evaluation(
        args.registration,
        args.evaluator_registration,
        args.baseline_manifest,
        args.ledger,
        args.refresh_audit,
        args.data,
        args.manifest,
        args.as_of,
        args.report,
    )
    print(json.dumps({key: value for key, value in report.items() if key != "result"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
