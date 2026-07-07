from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from health_report import HealthIssue
from notifier import Notifier


class TestNotifier(unittest.TestCase):
    def test_notify_issues_filters_below_min_severity(self):
        notifier = Notifier(webhook_url="https://example.test/hook", min_severity="critical")
        response = MagicMock()
        response.read.return_value = b"ok"
        response.__enter__.return_value = response
        issues = [
            HealthIssue("warning", "stale_order", "old order", {}),
            HealthIssue("critical", "api_failure", "exchange down", {}),
        ]

        with patch("notifier.urllib.request.urlopen", return_value=response) as urlopen:
            results = notifier.notify_issues(issues)

        self.assertEqual(1, len(results))
        body = urlopen.call_args.args[0].data.decode("utf-8")
        self.assertIn("api_failure", body)
        self.assertNotIn("stale_order", body)

    def test_notify_issues_returns_empty_when_all_issues_are_filtered(self):
        notifier = Notifier(webhook_url="https://example.test/hook", min_severity="critical")

        with patch("notifier.urllib.request.urlopen") as urlopen:
            results = notifier.notify_issues([HealthIssue("warning", "stale_order", "old order", {})])

        self.assertEqual([], results)
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
