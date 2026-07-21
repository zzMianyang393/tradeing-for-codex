"""Conservative structural sieve for the 111-prototype research universe."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


LOW_TURNOVER = {"低", "极低"}
ATTR = re.compile(r"\[([^:]+): ([^\]]+)\]")


def attributes(item: dict[str, Any]) -> dict[str, str]:
    return {key.strip(): value.strip() for key, value in ATTR.findall(str(item.get("attributes_raw", "")))}


def screen(item: dict[str, Any]) -> tuple[str, list[str]]:
    attr = attributes(item)
    reasons: list[str] = []
    name = f"{item['prototype_id']} {item['name_cn']} {item['description']}".lower()
    if item["status"] != "eligible_for_research":
        return "not_research_eligible", [f"draft status is {item['status']}"]
    if attr.get("免费可复现") != "是" or attr.get("受阻数据") != "否":
        reasons.append("data provenance does not satisfy the free reproducible gate")
    if attr.get("换手率") not in LOW_TURNOVER:
        reasons.append("turnover is not low")
    if attr.get("执行腿数") != "1":
        reasons.append("requires more than one execution leg")
    if attr.get("换壳嫌疑") != "否":
        reasons.append("draft marks the prototype as a rejected-family variant")
    if any(token in name for token in ("oi", "持仓", "funding", "费率", "交割", "价差", "套利", "期权", "宏观", "稳定币", "减半", "硬分叉", "板块")):
        reasons.append("requires a currently unavailable, multi-leg, or external-data mechanism")
    if any(token in name for token in ("donchian", "均线交叉", "均幅", "atr 通道", "历史新高", "突破")):
        reasons.append("trend/breakout mechanism overlaps the existing prospective trend sleeves")
    if reasons:
        return "structurally_deferred", reasons
    return "research_card_priority", ["single-leg, low-turnover, OHLCV-only mechanism with no declared rejected-family overlap"]


def build_report(universe: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in universe["prototypes"]:
        decision, reasons = screen(item)
        results.append({"prototype_id": item["prototype_id"], "name_cn": item["name_cn"], "draft_status": item["status"],
                        "decision": decision, "reasons": reasons, "attributes": attributes(item)})
    counts: dict[str, int] = {}
    for item in results:
        counts[item["decision"]] = counts.get(item["decision"], 0) + 1
    priority = [item for item in results if item["decision"] == "research_card_priority"]
    return {"report_type": "strategy_prototype_batch_preflight", "source_prototype_count": len(results), "decision_counts": dict(sorted(counts.items())),
            "research_card_priority": priority, "results": results,
            "methodology_notes": ["This is a structural screen, not a performance backtest.", "Priority means eligible to receive a frozen research card only; it does not mean approved or paper eligible.", "Existing prospective trend sleeves are treated as overlap risks, not as approval evidence."],
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=Path, default=Path("reports/strategy_prototype_universe_111.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/strategy_prototype_batch_preflight.json"))
    args = parser.parse_args()
    report = build_report(json.loads(args.universe.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"priority={len(report['research_card_priority'])}; decisions={report['decision_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
