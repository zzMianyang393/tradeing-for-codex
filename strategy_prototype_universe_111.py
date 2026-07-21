"""Parse the frozen 111-prototype draft into a machine-readable research universe."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ITEM = re.compile(r"^\d+\. \*\*([A-Z]+_\d+): ([^*]+)\*\*")
STATUS = re.compile(r"状态：`([^`]+)`")


def parse_universe(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        match = ITEM.match(line.strip())
        if match:
            if current is not None:
                items.append(current)
            current = {"prototype_id": match.group(1), "name_cn": match.group(2).strip(), "description": "", "status": None}
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("- **描述：**"):
            current["description"] = stripped.removeprefix("- **描述：**").strip()
        status = STATUS.search(stripped)
        if status:
            current["status"] = status.group(1)
        if stripped.startswith("- 属性："):
            current["attributes_raw"] = stripped.removeprefix("- 属性：").strip()
    if current is not None:
        items.append(current)
    if len(items) != 111 or any(item["status"] is None for item in items):
        raise ValueError(f"expected 111 fully classified prototypes, found {len(items)}")
    return items


def build_report(source: Path) -> dict[str, Any]:
    items = parse_universe(source.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for item in items:
        counts[str(item["status"])] = counts.get(str(item["status"]), 0) + 1
    return {"report_type": "strategy_prototype_universe_111", "source": str(source), "prototype_count": len(items),
            "status_counts": dict(sorted(counts.items())), "prototypes": items,
            "methodology_notes": ["Parsed from the frozen draft; no prototype is approved by this export.", "This report does not run a backtest or change a strategy status."],
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("docs/strategy_prototype_universe_100_draft_2026-07-13.md"))
    parser.add_argument("--out", type=Path, default=Path("reports/strategy_prototype_universe_111.json"))
    args = parser.parse_args()
    report = build_report(args.source)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"prototypes={report['prototype_count']}; statuses={report['status_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
