"""Aggregate strategy status from local registries into reports/prod + docs."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_metrics(j: dict) -> dict:
    m: dict = {}
    for key in (
        "return_pct",
        "total_return_pct",
        "net_return_pct",
        "return_fraction",
        "ending_equity",
        "profit_factor",
        "max_drawdown_pct",
        "max_drawdown_fraction",
        "trades",
        "n_trades",
        "formal_status",
        "status",
    ):
        if key in j:
            m[key] = j[key]
    acc = j.get("account") or j.get("account_summary") or {}
    if isinstance(acc, dict):
        for key in (
            "return_fraction",
            "ending_equity",
            "profit_factor",
            "max_drawdown_fraction",
            "trades",
            "wins",
        ):
            if key in acc:
                m[key] = acc[key]
    for nest in ("formation", "oos", "summary", "metrics", "result", "primary"):
        block = j.get(nest)
        if isinstance(block, dict):
            for key in (
                "return_pct",
                "net_return_pct",
                "profit_factor",
                "max_drawdown_pct",
                "max_drawdown_fraction",
                "trades",
                "status",
                "return_fraction",
            ):
                if key in block and key not in m:
                    m[key] = block[key]
    return m


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    records = (_load(root / "reports/research_approval_registry.json").get("records") or [])
    pros = _load(root / "reports/prospective_candidate_registry.json")
    pri = _load(root / "reports/priority_research_queue_audit.json")
    dash = root / "docs/research_state_dashboard_2026-07-16.md"

    rows: list[dict] = []
    for r in records:
        rid = r.get("research_id") or r.get("name_cn") or "?"
        rows.append(
            {
                "id": rid,
                "name_cn": r.get("name_cn") or "",
                "status": r.get("status"),
                "eligible_for_paper": bool(r.get("eligible_for_paper")),
                "reason": (r.get("reason") or "")[:300],
                "evidence": r.get("evidence_paths") or r.get("evidence") or [],
                "source": "approval_registry",
            }
        )

    seen = {x["id"] for x in rows}
    for it in pri.get("items") or []:
        pid = it.get("prototype_id") or it.get("name_cn")
        if pid in seen:
            continue
        rows.append(
            {
                "id": pid,
                "name_cn": it.get("name_cn") or "",
                "status": it.get("queue_status"),
                "eligible_for_paper": False,
                "reason": f"priority_queue; source={it.get('source_report')}",
                "evidence": [it.get("source_report")] if it.get("source_report") else [],
                "source": "priority_queue",
            }
        )
        seen.add(pid)

    for x in pros.get("frozen_candidates") or []:
        rows.append(
            {
                "id": x.get("candidate_id"),
                "name_cn": "",
                "status": x.get("status"),
                "eligible_for_paper": False,
                "reason": (
                    f"hist_ret%={x.get('historical_observed_return_pct')} "
                    f"maxDD%={x.get('historical_observed_max_drawdown_pct')} "
                    f"positions={x.get('historical_observed_accepted_positions')} "
                    f"prospective_start={x.get('prospective_start')}"
                ),
                "evidence": x.get("evidence") or [],
                "source": "prospective_frozen",
                "hist_return_pct": x.get("historical_observed_return_pct"),
                "hist_dd_pct": x.get("historical_observed_max_drawdown_pct"),
                "hist_positions": x.get("historical_observed_accepted_positions"),
            }
        )
    for x in pros.get("watchlist") or []:
        rows.append(
            {
                "id": x.get("candidate_id"),
                "name_cn": "",
                "status": x.get("status"),
                "eligible_for_paper": False,
                "reason": (x.get("reason") or x.get("display_summary") or "")[:300],
                "evidence": x.get("evidence") or [],
                "source": "prospective_watchlist",
                "display": x.get("display_summary"),
            }
        )

    # ten_u special
    for ten_u in (
        root / "reports/ten_u_event_trend_screen_v2.json",
        root / "reports/ten_u_event_trend_goal_audit_v2.json",
        root / "docs/ten_u_warlord_formation_result_v1.md",
    ):
        pass
    rows.append(
        {
            "id": "ten_u_single_symbol_persistent_event_trend_48h_v2",
            "name_cn": "10U 战神 Event Trend v2",
            "status": "active_research_not_validated",
            "eligible_for_paper": False,
            "reason": (
                "sealed_screen_insufficient_evidence (3 trades); dominated by RAVE; "
                "prod paper-prep only; not live-authorized"
            ),
            "evidence": [
                "reports/ten_u_event_trend_screen_v2.json",
                "reports/ten_u_event_trend_informal_full_history_v2.json",
            ],
            "source": "ten_u",
            "hist_return_pct": 1950.06,
            "hist_dd_pct": 18.74,
            "hist_note": "sealed 45d 3 trades 10->205; informal full ~23 trades ~209",
        }
    )
    rows.append(
        {
            "id": "ten_u_trend_breakout_v1",
            "name_cn": "10U Warlord 趋势突破 v1",
            "status": "rejected_at_formation",
            "eligible_for_paper": False,
            "reason": "Formation -41.12% PF 0.87 across 123 trades; validation sealed",
            "evidence": ["docs/ten_u_warlord_signal_card_v1.md"],
            "source": "ten_u",
            "hist_return_pct": -41.12,
        }
    )

    metric_hints: dict[str, dict] = {}
    for r in rows:
        for ev in r.get("evidence") or []:
            p = root / str(ev).replace("\\", "/")
            if not p.exists():
                p2 = root / "reports" / Path(str(ev)).name
                p = p2 if p2.exists() else p
            if p.exists() and p.suffix == ".json":
                try:
                    j = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                m = _extract_metrics(j)
                if m:
                    metric_hints[r["id"]] = {"file": str(p.as_posix()), **m}

    # combo baseline
    rows.append(
        {
            "id": "historical_four_sleeve_shared_capital_combo",
            "name_cn": "四袖套共享资金组合基线",
            "status": "historical_walk_forward_rejected",
            "eligible_for_paper": False,
            "reason": "WF return ~-64.4% maxDD ~66.9%; 0/5 positive half-year windows; sealed diagnostic",
            "evidence": ["docs/research_state_dashboard_2026-07-16.md"],
            "source": "combo_baseline",
            "hist_return_pct": -64.39,
            "hist_dd_pct": 66.90,
        }
    )

    out = {
        "as_of": "2026-07-17",
        "note": (
            "Aggregated from research_approval_registry, priority queue, "
            "prospective registry, and 10U docs. Metrics best-effort from evidence JSON."
        ),
        "eligible_for_paper_any": any(r.get("eligible_for_paper") for r in rows),
        "counts_by_status": dict(Counter(r["status"] for r in rows)),
        "counts_by_source": dict(Counter(r["source"] for r in rows)),
        "strategies": rows,
        "metric_hints": metric_hints,
        "dashboard_ref": str(dash) if dash.exists() else None,
    }

    out_path = root / "reports/prod/strategy_status_inventory.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    order = [
        "rejected",
        "historical_rejected",
        "rejected_at_formation",
        "invalid",
        "risk_blocked",
        "historical_walk_forward_rejected",
        "frozen",
        "frozen_awaiting_prospective",
        "meta_only",
        "insufficient_evidence",
        "legacy_limited_scope_evidence",
        "observation_only",
        "requires_specification",
        "active_research_not_validated",
        "watchlist_concentration_risk",
        "posthoc_directional_weak_feature_watchlist",
        "posthoc_sleeve_weak_feature_watchlist",
        "posthoc_regime_sleeve_weak_feature_watchlist",
        "combo_watchlist_strict_gate_failed",
        "prospective_pair_comparison_only",
        "rejected_standalone_regime_gated_weak_feature_watchlist",
    ]
    by_status: dict[str, list] = defaultdict(list)
    for r in rows:
        by_status[r["status"] or "unknown"].append(r)

    md: list[str] = []
    md.append("# 策略全景清单（历史研究注册表汇总）\n\n")
    md.append(f"生成：{out['as_of']}\n\n")
    md.append(f"- 条目数：**{len(rows)}**\n")
    md.append(f"- 任一 `eligible_for_paper`：**{out['eligible_for_paper_any']}**\n")
    md.append(f"- 状态计数：`{out['counts_by_status']}`\n")
    md.append(f"- 机器可读：`reports/prod/strategy_status_inventory.json`\n\n")
    md.append("## 总结论\n\n")
    md.append(
        "**没有任何策略获准模拟盘或实盘。** 下表「历史收益」来自旧报告/观察字段，"
        "不等于可交易 edge；很多高收益是集中度/短窗/污染样本。\n\n"
    )
    md.append("### 失败原因类型（读表时对照）\n\n")
    md.append("| 类型 | 含义 |\n|------|------|\n")
    md.append("| rejected / historical_rejected | 按预注册闸门失败或样本外失效 |\n")
    md.append("| invalid | 方法错误/标签污染/不可当证据 |\n")
    md.append("| risk_blocked | 风险结构禁止（网格/马丁等） |\n")
    md.append("| insufficient_evidence | 样本/稳定性不够，不判过 |\n")
    md.append("| frozen_awaiting_prospective | 历史好看但未前瞻证明 |\n")
    md.append("| watchlist_* / concentration | 有正贡献但过度集中或事后挑选 |\n")
    md.append("| combo_*_failed | 组合严格闸门未过 |\n")
    md.append("| active_research_not_validated | 在研未验证（如 10U v2） |\n\n")

    for st in order + sorted(set(by_status) - set(order)):
        items = by_status.get(st) or []
        if not items:
            continue
        md.append(f"## {st}（{len(items)}）\n\n")
        md.append("| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |\n")
        md.append("|----|------|--------------|----------------------|\n")
        for r in sorted(items, key=lambda x: str(x.get("id") or "")):
            mid = r.get("id") or ""
            mh = metric_hints.get(mid) or {}
            hist = ""
            if r.get("hist_return_pct") is not None:
                hist = f"ret≈{float(r['hist_return_pct']):.2f}%"
                if r.get("hist_dd_pct") is not None:
                    hist += f", DD≈{float(r['hist_dd_pct']):.2f}%"
                if r.get("hist_note"):
                    hist += f" ({r['hist_note']})"
            elif "return_fraction" in mh:
                hist = f"ret≈{float(mh['return_fraction']) * 100:.2f}%"
                if "max_drawdown_fraction" in mh:
                    hist += f", DD≈{float(mh['max_drawdown_fraction']) * 100:.2f}%"
                if "profit_factor" in mh:
                    hist += f", PF≈{mh['profit_factor']}"
            elif "return_pct" in mh:
                hist = f"ret≈{mh['return_pct']}"
            elif "net_return_pct" in mh:
                hist = f"net≈{mh['net_return_pct']}"
            elif r.get("display"):
                hist = str(r["display"])[:70]
            else:
                hist = "（无解析数字）"
            reason = (r.get("reason") or "").replace("|", "\\|").replace("\n", " ")[:140]
            name = (r.get("name_cn") or "").replace("|", "\\|")[:36]
            md.append(f"| `{mid}` | {name} | {hist} | {reason} |\n")
        md.append("\n")

    md_path = root / "docs/strategy_status_inventory_2026-07-17.md"
    md_path.write_text("".join(md), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Wrote {md_path}")
    print("total", len(rows), "statuses", out["counts_by_status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
