"""Merge non-published RSI signal batches while preserving their signal-only schema."""
from __future__ import annotations

import json
from pathlib import Path

from cohort_b_signal_staging_assembler import build


def main() -> None:
    sources = []
    for index in range(1, 5):
        path = Path("reports") / f"rsi_staging_batch_{index}.json"
        sources.append((f"rsi_batch_{index}", json.loads(path.read_text(encoding="utf-8"))))
    report = build(sources)
    report["report_type"] = "prospective_cohort_b_rsi_staging_ledger"
    report["scope"] = "signal_only_current_cutoff_not_merged_not_committed"
    Path("reports/prospective_cohort_b_rsi_staging_ledger.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"signals={report['signal_count']}; cutoff={report['common_data_cutoff']}")


if __name__ == "__main__":
    main()
