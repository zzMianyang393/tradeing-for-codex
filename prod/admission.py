"""Paper-prep admission for the production track.

Design intent (user policy 2026-07-17):
- Prospective calendar waiting is NOT required for paper-prep.
- A strategy may enter paper-prep when historical replay looks usable and
  anti-overfit checks do not hard-fail.
- High-risk 10U sleeves may pass with concentration warnings if the operator
  explicitly accepts that risk; live still stays closed by default.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AdmissionThresholds:
    """Frozen paper-prep thresholds for the high-risk 10U sleeve."""

    minimum_trades: int = 6
    minimum_ending_equity: float = 10.0
    maximum_drawdown_fraction: float = 0.70
    minimum_profit_factor: float = 1.0
    # Soft anti-overfit: warn if one trade dominates; hard-fail only above this
    # when accept_concentration_risk is False.
    max_winner_share_soft: float = 0.50
    max_winner_share_hard: float = 0.90
    # Drop-max-winner equity must stay above ruin for non-high-risk paths.
    drop_max_winner_min_equity: float = 2.0
    require_not_ruined: bool = True


@dataclass
class AdmissionResult:
    strategy_id: str
    track: str
    decision: str
    paper_prep_allowed: bool
    live_allowed: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    config_fingerprint: str | None = None
    as_of: str = ""
    operator_flags: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def max_winner_share(trades: list[dict[str, Any]]) -> float:
    wins = [float(t.get("net_pnl", 0.0)) for t in trades if float(t.get("net_pnl", 0.0)) > 0]
    if not wins:
        return 0.0
    total = sum(wins)
    if total <= 0:
        return 0.0
    return max(wins) / total


def equity_after_drop_max_winner(
    starting_equity: float,
    trades: list[dict[str, Any]],
) -> float:
    """Recompute terminal equity as if the single best trade never happened."""
    if not trades:
        return starting_equity
    best_i = max(range(len(trades)), key=lambda i: float(trades[i].get("net_pnl", 0.0)))
    equity = starting_equity
    for i, trade in enumerate(trades):
        if i == best_i:
            continue
        equity = max(0.0, equity + float(trade.get("net_pnl", 0.0)))
    return equity


def admit_from_account_summary(
    *,
    strategy_id: str,
    track: str,
    account: dict[str, Any],
    config_fingerprint: str | None = None,
    thresholds: AdmissionThresholds | None = None,
    accept_concentration_risk: bool = False,
    high_risk_sleeve: bool = False,
) -> AdmissionResult:
    """Admit using a finished account replay summary + optional trades_detail."""
    thr = thresholds or AdmissionThresholds()
    reasons: list[str] = []
    warnings: list[str] = []

    trades_n = int(account.get("trades", 0))
    ending = float(account.get("ending_equity", 0.0))
    starting = float(account.get("starting_equity", 10.0))
    max_dd = float(account.get("max_drawdown_fraction", 1.0))
    pf = float(account.get("profit_factor", 0.0))
    permanent = str(account.get("permanent_account_state", "active_or_temporary_cooldown"))
    trades_detail = list(account.get("trades_detail") or account.get("trades") or [])
    # trades_detail may be list of dicts; if account["trades"] is int, ignore
    if trades_detail and isinstance(trades_detail[0], (int, float)):
        trades_detail = list(account.get("trades_detail") or [])

    share = 0.0
    drop_eq = starting
    if trades_detail and isinstance(trades_detail[0], dict):
        share = max_winner_share(trades_detail)
        drop_eq = equity_after_drop_max_winner(starting, trades_detail)

    metrics = {
        "trades": trades_n,
        "starting_equity": starting,
        "ending_equity": ending,
        "return_fraction": ending / starting - 1.0 if starting else 0.0,
        "max_drawdown_fraction": max_dd,
        "profit_factor": pf if pf < 1e8 else None,
        "max_winner_share": share,
        "equity_after_drop_max_winner": drop_eq,
        "permanent_account_state": permanent,
    }

    if trades_n < thr.minimum_trades:
        reasons.append("trades_below_minimum")
    if ending < thr.minimum_ending_equity:
        reasons.append("ending_equity_below_start_or_floor")
    if max_dd > thr.maximum_drawdown_fraction:
        reasons.append("drawdown_above_maximum")
    if pf < thr.minimum_profit_factor and pf < 1e8:
        reasons.append("profit_factor_below_minimum")
    if thr.require_not_ruined and permanent in {"ruined", "peak_drawdown_halt"}:
        reasons.append(f"account_terminal_state_{permanent}")

    if share >= thr.max_winner_share_soft:
        warnings.append(
            f"max_winner_share={share:.2%} exceeds soft threshold {thr.max_winner_share_soft:.0%}"
        )
    if share >= thr.max_winner_share_hard:
        if high_risk_sleeve and accept_concentration_risk:
            warnings.append(
                "max_winner_share above hard threshold but accepted for high-risk paper-prep"
            )
        else:
            reasons.append("max_winner_share_above_hard_threshold")

    if drop_eq < thr.drop_max_winner_min_equity:
        if high_risk_sleeve and accept_concentration_risk:
            warnings.append(
                f"drop_max_winner equity {drop_eq:.2f} below ruin floor but accepted for high-risk paper-prep"
            )
        else:
            reasons.append("drop_max_winner_below_ruin_floor")

    paper_ok = not reasons
    # Live always closed from this gate alone — separate promotion step.
    live_ok = False
    if paper_ok and not warnings:
        decision = "paper_prep_allowed"
    elif paper_ok and warnings:
        decision = "paper_prep_allowed_with_warnings"
    else:
        decision = "rejected_for_paper_prep"

    return AdmissionResult(
        strategy_id=strategy_id,
        track=track,
        decision=decision,
        paper_prep_allowed=paper_ok,
        live_allowed=live_ok,
        reasons=reasons,
        warnings=warnings,
        metrics=metrics,
        config_fingerprint=config_fingerprint,
        as_of=_utc_now(),
        operator_flags={
            "accept_concentration_risk": accept_concentration_risk,
            "high_risk_sleeve": high_risk_sleeve,
            "prospective_wait_required": False,
            "live_requires_separate_promotion": True,
        },
    )


def admit_ten_u_from_report(
    report_path: Path,
    *,
    accept_concentration_risk: bool = True,
    high_risk_sleeve: bool = True,
    thresholds: AdmissionThresholds | None = None,
) -> AdmissionResult:
    """Load a screen / informal full-history style report and admit 10U v2."""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    account = report.get("account") or report.get("account_summary")
    if account is None:
        raise ValueError(f"no account summary in {report_path}")
    # informal report stores trades separately
    if "trades_detail" not in account and "trades" in report and isinstance(report["trades"], list):
        account = dict(account)
        account["trades_detail"] = report["trades"]
        # informal trades list may lack full fields; map net_pnl if present
    strategy_id = report.get("strategy_id") or "ten_u_single_symbol_persistent_event_trend_48h_v2"
    fingerprint = report.get("config_fingerprint")
    return admit_from_account_summary(
        strategy_id=strategy_id,
        track="ten_u_high_risk",
        account=account,
        config_fingerprint=fingerprint,
        thresholds=thresholds,
        accept_concentration_risk=accept_concentration_risk,
        high_risk_sleeve=high_risk_sleeve,
    )


def write_admission_report(result: AdmissionResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
