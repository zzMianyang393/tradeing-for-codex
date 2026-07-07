from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class HealthIssue:
    severity: str
    kind: str
    message: str
    context: dict[str, Any]


@dataclass(frozen=True)
class HealthReport:
    status: str
    generated_at: str
    issues: list[HealthIssue]
    pending_orders: int
    local_open_positions: int
    exchange_open_positions: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [asdict(issue) for issue in self.issues]
        return payload


def build_health_report(
    *,
    active_orders: list[dict],
    reconciliation: Any | None = None,
    risk_status: Any | None = None,
    api_error: str = "",
    now: datetime | None = None,
    stale_order_minutes: int = 30,
    local_open_positions: int = 0,
    exchange_open_positions: int | None = None,
) -> HealthReport:
    generated_at = now or datetime.now(timezone.utc)
    issues: list[HealthIssue] = []

    if api_error:
        issues.append(
            HealthIssue(
                severity="critical",
                kind="api_failure",
                message=f"Exchange API check failed: {api_error}",
                context={"error": api_error},
            )
        )

    if reconciliation is not None and not _get_value(reconciliation, "consistent", True):
        local_only = _get_value(reconciliation, "local_only", [])
        exchange_only = _get_value(reconciliation, "exchange_only", [])
        issues.append(
            HealthIssue(
                severity="critical",
                kind="reconciliation_drift",
                message="Local positions do not match exchange positions",
                context={
                    "local_only": local_only,
                    "exchange_only": exchange_only,
                    "local_only_count": len(local_only),
                    "exchange_only_count": len(exchange_only),
                },
            )
        )

    if _is_risk_paused(risk_status):
        reason = _get_value(risk_status, "pause_reason", "") or _get_value(risk_status, "reason", "")
        issues.append(
            HealthIssue(
                severity="warning",
                kind="risk_paused",
                message="Risk manager is paused",
                context={"reason": reason},
            )
        )

    for order in active_orders:
        created_at = _parse_utc(order.get("created_at"))
        if created_at is None:
            continue
        age_minutes = int((generated_at - created_at).total_seconds() // 60)
        if age_minutes >= stale_order_minutes:
            issues.append(
                HealthIssue(
                    severity="warning",
                    kind="stale_order",
                    message=f"Active order has been pending for {age_minutes} minutes",
                    context={
                        "order_id": order.get("id"),
                        "exchange_order_id": order.get("exchange_order_id"),
                        "symbol": order.get("symbol"),
                        "status": order.get("status"),
                        "age_minutes": age_minutes,
                    },
                )
            )

    return HealthReport(
        status=_overall_status(issues),
        generated_at=generated_at.strftime("%Y-%m-%d %H:%M:%S"),
        issues=issues,
        pending_orders=len(active_orders),
        local_open_positions=local_open_positions,
        exchange_open_positions=exchange_open_positions,
    )


def _overall_status(issues: list[HealthIssue]) -> str:
    if any(issue.severity == "critical" for issue in issues):
        return "critical"
    if issues:
        return "warning"
    return "ok"


def _is_risk_paused(risk_status: Any | None) -> bool:
    if risk_status is None:
        return False
    return bool(_get_value(risk_status, "is_paused", False) or _get_value(risk_status, "paused", False))


def _get_value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class HealthAlertTracker:
    """Tracks recently notified issues to suppress duplicate alerts.

    Args:
        suppress_minutes: How long to suppress repeated alerts of the same kind+symbol.
        min_severity: Minimum severity level to notify ("warning" or "critical").
    """

    def __init__(self, suppress_minutes: float = 60.0, min_severity: str = "warning") -> None:
        self.suppress_minutes = suppress_minutes
        self.min_severity = min_severity
        self._recent: dict[str, float] = {}  # alert_key -> last_notified_timestamp

    def filter_new_issues(self, issues: list[HealthIssue]) -> list[HealthIssue]:
        """Return only issues that haven't been notified recently."""
        now = time.monotonic()
        cutoff = now - self.suppress_minutes * 60.0
        # Clean old entries
        self._recent = {k: v for k, v in self._recent.items() if v > cutoff}

        severity_order = {"ok": 0, "warning": 1, "critical": 2}
        min_level = severity_order.get(self.min_severity, 1)

        new_issues: list[HealthIssue] = []
        for issue in issues:
            level = severity_order.get(issue.severity, 0)
            if level < min_level:
                continue
            key = self._alert_key(issue)
            if key in self._recent:
                continue
            self._recent[key] = now
            new_issues.append(issue)
        return new_issues

    @staticmethod
    def _alert_key(issue: HealthIssue) -> str:
        ctx = issue.context or {}
        symbol = ctx.get("symbol", "")
        return f"{issue.kind}:{symbol}"
