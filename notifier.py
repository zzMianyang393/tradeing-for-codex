"""External alert notification delivery.

Supports Webhook (generic HTTP POST) and Telegram Bot API.
Configuration is read from environment variables:

    NOTIFY_WEBHOOK_URL          - Webhook URL for HTTP POST
    NOTIFY_TELEGRAM_BOT_TOKEN   - Telegram bot token
    NOTIFY_TELEGRAM_CHAT_ID     - Telegram chat ID

Only issues with severity >= min_severity are sent.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("notifier")


@dataclass
class NotificationResult:
    channel: str
    success: bool
    error: str = ""


class Notifier:
    """Sends health alert notifications to external channels."""

    def __init__(
        self,
        webhook_url: str = "",
        telegram_bot_token: str = "",
        telegram_chat_id: str = "",
        min_severity: str = "warning",
    ) -> None:
        self.webhook_url = webhook_url or os.environ.get("NOTIFY_WEBHOOK_URL", "")
        self.telegram_bot_token = telegram_bot_token or os.environ.get("NOTIFY_TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = telegram_chat_id or os.environ.get("NOTIFY_TELEGRAM_CHAT_ID", "")
        self.min_severity = min_severity

    @property
    def has_channels(self) -> bool:
        return bool(self.webhook_url or (self.telegram_bot_token and self.telegram_chat_id))

    def notify_issues(self, issues: list[Any]) -> list[NotificationResult]:
        """Send alert notifications for the given health issues."""
        filtered = self._filter_by_severity(issues)
        if not filtered or not self.has_channels:
            return []

        message = self._format_message(filtered)
        results: list[NotificationResult] = []

        if self.webhook_url:
            results.append(self._send_webhook(message, filtered))

        if self.telegram_bot_token and self.telegram_chat_id:
            results.append(self._send_telegram(message))

        return results

    def _filter_by_severity(self, issues: list[Any]) -> list[Any]:
        severity_order = {"ok": 0, "warning": 1, "critical": 2}
        min_level = severity_order.get(self.min_severity, 1)
        return [
            issue
            for issue in issues
            if severity_order.get(getattr(issue, "severity", ""), 0) >= min_level
        ]

    def _format_message(self, issues: list[Any]) -> str:
        """Format issues into a readable alert message."""
        lines = ["Trading Alert"]
        for issue in issues:
            severity = getattr(issue, "severity", "unknown")
            kind = getattr(issue, "kind", "unknown")
            msg = getattr(issue, "message", "")
            lines.append(f"[{severity.upper()}] {kind}: {msg}")
        return "\n".join(lines)

    def _send_webhook(self, message: str, issues: list[Any]) -> NotificationResult:
        """Send alert via generic HTTP POST webhook."""
        payload = {
            "text": message,
            "message": message,
            "issues": [
                {
                    "severity": getattr(issue, "severity", ""),
                    "kind": getattr(issue, "kind", ""),
                    "message": getattr(issue, "message", ""),
                    "context": getattr(issue, "context", {}),
                }
                for issue in issues
            ],
        }
        body = json.dumps(payload, default=str).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
            return NotificationResult(channel="webhook", success=True)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            logger.warning("Webhook notification failed: %s", exc)
            return NotificationResult(channel="webhook", success=False, error=str(exc))

    def _send_telegram(self, message: str) -> NotificationResult:
        """Send alert via Telegram Bot API."""
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        body = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
            return NotificationResult(channel="telegram", success=True)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            logger.warning("Telegram notification failed: %s", exc)
            return NotificationResult(channel="telegram", success=False, error=str(exc))


def create_notifier_from_env() -> Notifier:
    """Create a Notifier using environment variables."""
    return Notifier(
        webhook_url=os.environ.get("NOTIFY_WEBHOOK_URL", ""),
        telegram_bot_token=os.environ.get("NOTIFY_TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("NOTIFY_TELEGRAM_CHAT_ID", ""),
    )
