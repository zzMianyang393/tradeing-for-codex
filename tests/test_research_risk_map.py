from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_risk_map import build_risk_map


class ResearchRiskMapTests(unittest.TestCase):
    def test_build_risk_map_preserves_no_trading_permission(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            reports = Path(tmp)
            (reports / "research_approval_registry.json").write_text(
                json.dumps(
                    {
                        "status_counts": {"rejected": 17, "meta_only": 9},
                        "approved_for_paper": [],
                        "approved_research": [],
                        "safe_to_enable_trading": False,
                    }
                ),
                encoding="utf-8",
            )
            (reports / "execution_cost_floor_audit.json").write_text(
                json.dumps(
                    {
                        "scenarios": [
                            {"name": "single_market_directional_round_trip", "round_trip_cost": 0.0016},
                            {"name": "two_market_neutral_round_trip", "round_trip_cost": 0.0032},
                            {"name": "calendar_spread_round_trip", "round_trip_cost": 0.0032},
                        ],
                        "hard_rules": ["cost floor"],
                    }
                ),
                encoding="utf-8",
            )
            (reports / "low_turnover_research_gate.json").write_text(
                json.dumps({"thresholds": {"min_hold_days": 3.0}, "hard_rules": ["low turnover"]}),
                encoding="utf-8",
            )
            (reports / "no_trade_filter_research.json").write_text(
                json.dumps({"n_events_analysed": 27, "n_reports_processed": 3, "filter_candidates": [{"value": "2024-12"}]}),
                encoding="utf-8",
            )
            (reports / "oi_deleveraging_filter_audit.json").write_text(
                json.dumps(
                    {
                        "summary": {
                            "formation": {"events": 451, "abs_fwd_3d": {"mean_pct": 6.3}, "abs_fwd_7d": {"mean_pct": 9.8}},
                            "oos": {"events": 53, "abs_fwd_3d": {"mean_pct": 3.4}, "abs_fwd_7d": {"mean_pct": 4.9}},
                        },
                        "verdict": {"eligible_for_strategy": False, "eligible_as_hard_filter": False},
                    }
                ),
                encoding="utf-8",
            )
            risk_map = build_risk_map(reports)
        self.assertFalse(risk_map["trading_permission"]["safe_to_enable_trading"])
        self.assertEqual([], risk_map["trading_permission"]["approved_for_paper"])
        self.assertEqual(0.0032, risk_map["cost_constraints"]["two_market_round_trip_cost"])
        self.assertEqual("weak_observation_only", risk_map["failure_filter_observations"]["evidence_level"])
        self.assertEqual("context_label_only", risk_map["risk_state_labels"][0]["allowed_use"])
        self.assertIn("entry_signal", risk_map["risk_state_labels"][0]["not_allowed"])


if __name__ == "__main__":
    unittest.main()
