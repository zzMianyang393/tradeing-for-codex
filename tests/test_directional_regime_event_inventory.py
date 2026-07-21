from __future__ import annotations

import json
from pathlib import Path

from directional_regime_event_inventory import (
    best_oos_regime,
    build_report,
    summarize,
    summarize_by_regime,
)


def test_summarize_reports_return_distribution():
    result = summarize([2.0, -1.0, 3.0])

    assert result["observations"] == 3
    assert result["net_sum_pct"] == 4.0
    assert result["win_rate"] == 0.666667
    assert result["profit_factor"] == 5.0


def test_summarize_by_regime_keeps_split_separate():
    events = [
        {"split": "formation", "entry_regime": "震荡", "net_return_pct": 1.0},
        {"split": "oos", "entry_regime": "震荡", "net_return_pct": 2.0},
        {"split": "oos", "entry_regime": "趋势上行", "net_return_pct": -1.0},
    ]

    result = summarize_by_regime(events, "oos")

    assert result["震荡"]["net_sum_pct"] == 2.0
    assert result["趋势上行"]["net_sum_pct"] == -1.0


def test_best_oos_regime_requires_minimum_events():
    result = best_oos_regime({"震荡": {"observations": 9, "mean_pct": 10.0, "net_sum_pct": 90.0}})

    assert result["status"] == "no_regime_with_min_10_oos_events"


def test_best_oos_regime_selects_highest_mean_then_net_sum():
    result = best_oos_regime(
        {
            "震荡": {"observations": 12, "mean_pct": 1.0, "net_sum_pct": 12.0, "win_rate": 0.5},
            "趋势上行": {"observations": 11, "mean_pct": 2.0, "net_sum_pct": 22.0, "win_rate": 0.6},
        }
    )

    assert result["status"] == "ok"
    assert result["regime"] == "趋势上行"
    assert result["observations"] == 11


def test_build_report_reads_existing_regime_reports(tmp_path: Path):
    source = tmp_path / "sample_regime_report.json"
    source.write_text(
        json.dumps(
            {
                "verdict": {"status": "regime_conditioned_rejected"},
                "events": [
                    {"split": "formation", "entry_regime": "震荡", "net_return_pct": 1.0},
                    {"split": "oos", "entry_regime": "震荡", "net_return_pct": 2.0},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_report({"sample": source})

    assert result["reviews"]["sample"]["status"] == "ok"
    assert result["reviews"]["sample"]["raw_events"] == 2
    assert result["reviews"]["sample"]["oos_by_regime"]["震荡"]["net_sum_pct"] == 2.0
    assert result["safety_gates"]["approved_for_paper"] == []
    assert result["safety_gates"]["safe_to_enable_trading"] is False
    assert result["safety_gates"]["ready_for_combo_backtest"] is False


def test_build_report_marks_missing_reports(tmp_path: Path):
    result = build_report({"missing": tmp_path / "missing.json"})

    assert result["reviews"]["missing"]["status"] == "missing_report"
