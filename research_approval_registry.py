"""Machine-readable registry for research conclusions and trading approval.

This registry is deliberately separate from strategy code.  Its job is to make
research status explicit: an attractive historical report is not permission to
run a strategy unless it has been explicitly approved here.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path


class ResearchStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    INVALID = "invalid"
    PENDING = "pending"
    CANDIDATE = "candidate"
    FROZEN = "frozen"
    DATA_BLOCKED = "data_blocked"
    RISK_BLOCKED = "risk_blocked"
    META_ONLY = "meta_only"


@dataclass(frozen=True)
class ResearchRecord:
    research_id: str
    name_cn: str
    status: ResearchStatus
    eligible_for_paper: bool
    reason: str
    evidence_paths: tuple[str, ...]


def records() -> tuple[ResearchRecord, ...]:
    """Return the current decision ledger, not a list of runnable strategies."""
    return (
        ResearchRecord(
            "legacy_dynamic_router",
            "旧动态路由高收益报告",
            ResearchStatus.INVALID,
            False,
            "旧配置、路由复用与 MFE 标签问题使历史高收益不可作为策略证据。",
            ("docs/research_decision_2026-07-10.md",),
        ),
        ResearchRecord(
            "relative_strength_persistence",
            "相对强弱持续",
            ResearchStatus.REJECTED,
            False,
            "样本外失败，高延伸追强组入场质量更差。",
            ("reports/rs_persistence_entry_timing_audit.json",),
        ),
        ResearchRecord(
            "btc_trend_pullback",
            "BTC 趋势内山寨回调",
            ResearchStatus.REJECTED,
            False,
            "形成期整体亏损，理论适用的趋势上行标签同样为负。",
            ("reports/btc_trend_pullback_regime_formation.json",),
        ),
        ResearchRecord(
            "vol_compression_breakout",
            "波动率压缩突破",
            ResearchStatus.REJECTED,
            False,
            "样本不足且完整验证失败。",
            ("reports/vol_compression_breakout_entry_timing_audit.json",),
        ),
        ResearchRecord(
            "pairs_walk_forward",
            "配对统计套利",
            ResearchStatus.REJECTED,
            False,
            "无配对通过严格形成期、样本外和多重检验门槛。",
            ("reports/pairs_walk_forward_v1.json",),
        ),
        ResearchRecord(
            "spot_perp_basis",
            "期现基差套利",
            ResearchStatus.REJECTED,
            False,
            "基差幅度不足以覆盖完整四腿成本。",
            ("reports/okx_basis_audit.json", "reports/basis_microstructure_audit.json"),
        ),
        ResearchRecord(
            "multi_coin_funding_crowding",
            "多币种资金费率拥挤反转",
            ResearchStatus.REJECTED,
            False,
            "事件收益为负且无法覆盖成本。",
            ("reports/multi_coin_funding_crowding_audit.json",),
        ),
        ResearchRecord(
            "funding_oi_joint_original",
            "Funding 与 OI 联合信号（原始报告）",
            ResearchStatus.INVALID,
            False,
            "将当天完整 funding 与日线 OI 用于当天 00:00 入场，存在前视偏差。",
            (
                "reports/funding_oi_joint_audit.json",
                "reports/funding_oi_joint_full_audit.json",
            ),
        ),
        ResearchRecord(
            "btc_alt_lead_lag",
            "BTC 对非 BTC 短时领先滞后",
            ResearchStatus.REJECTED,
            False,
            "形成期成本前后均为负。",
            ("reports/btc_alt_lead_lag_formation.json",),
        ),
        ResearchRecord(
            "positive_funding_carry",
            "正资金费率市场中性持有",
            ResearchStatus.REJECTED,
            False,
            "形成期没有足以覆盖四腿成本的合格事件。",
            ("reports/funding_carry_formation.json",),
        ),
        ResearchRecord(
            "funding_term_carry",
            "中周期 Funding Term Carry",
            ResearchStatus.REJECTED,
            False,
            "14 天 funding 收入均值不足以覆盖 0.32% 四腿往返成本，形成期与样本外净均值均为负。",
            (
                "docs/funding_term_carry_audit_2026-07-12.md",
                "reports/funding_term_carry_audit.json",
            ),
        ),
        ResearchRecord(
            "cross_time_stability",
            "跨时间稳定性元审计",
            ResearchStatus.META_ONLY,
            False,
            "用于约束数据和研究设计，不产生开仓信号。",
            ("reports/cross_time_stability_audit.json",),
        ),
        ResearchRecord(
            "execution_cost_floor",
            "执行成本地板元审计",
            ResearchStatus.META_ONLY,
            False,
            "用于约束未来研究的最低毛收益门槛，不产生开仓信号。",
            (
                "docs/execution_cost_floor_audit_2026-07-12.md",
                "reports/execution_cost_floor_audit.json",
            ),
        ),
        ResearchRecord(
            "low_turnover_research_gate",
            "低换手研究门槛元审计",
            ResearchStatus.META_ONLY,
            False,
            "用于阻止未来研究回到高换手小边际参数搜索，不产生开仓信号。",
            (
                "docs/low_turnover_research_gate_2026-07-12.md",
                "reports/low_turnover_research_gate.json",
            ),
        ),
        ResearchRecord(
            "no_trade_filter_research",
            "不交易过滤器候选元审计",
            ResearchStatus.META_ONLY,
            False,
            "用于从已淘汰报告中提取未来禁交易状态候选，样本有限且不产生开仓或过滤执行规则。",
            (
                "docs/no_trade_filter_research_2026-07-12.md",
                "reports/no_trade_filter_research.json",
            ),
        ),
        ResearchRecord(
            "okx_free_data_liquidity_map",
            "OKX 免费数据覆盖与流动性地图",
            ResearchStatus.META_ONLY,
            False,
            "用于约束可研究数据范围和流动性分层，不产生开仓信号。",
            ("docs/okx_free_data_liquidity_map_2026-07-12.md",),
        ),
        ResearchRecord(
            "rejected_strategy_failure_clusters",
            "已淘汰策略失败原因聚类",
            ResearchStatus.META_ONLY,
            False,
            "用于归纳已拒绝策略失败原因，防止换壳重跑，不产生开仓信号。",
            ("docs/rejected_strategy_failure_clusters_2026-07-12.md",),
        ),
        ResearchRecord(
            "frozen_family_reactivation_criteria",
            "冻结家族长期重启条件",
            ResearchStatus.META_ONLY,
            False,
            "用于约束冻结或风险受阻家族的未来重启条件，不产生开仓信号。",
            ("docs/frozen_family_reactivation_criteria_2026-07-12.md",),
        ),
        ResearchRecord(
            "low_turnover_public_research_scan",
            "低换手公开研究方向扫描",
            ResearchStatus.META_ONLY,
            False,
            "仅扫描未注册低换手研究方向，不批准候选策略或开仓信号。",
            ("docs/low_turnover_public_research_scan_2026-07-12.md",),
        ),
        ResearchRecord(
            "oi_deleveraging_filter",
            "OI 去杠杆过滤器元审计",
            ResearchStatus.META_ONLY,
            False,
            "用于识别高 OIVR 杠杆风险状态；不得作为开仓策略或硬性禁交易过滤器。",
            (
                "docs/oi_deleveraging_filter_audit_2026-07-13.md",
                "reports/oi_deleveraging_filter_audit.json",
            ),
        ),
        ResearchRecord(
            "research_risk_map",
            "研究风险地图",
            ResearchStatus.META_ONLY,
            False,
            "聚合成本、换手、弱过滤器候选与 OI 风险状态；仅作为研究前置闸门，不产生交易信号。",
            (
                "docs/research_risk_map_2026-07-13.md",
                "reports/research_risk_map.json",
            ),
        ),
        ResearchRecord(
            "funding_oi_time_corrected",
            "Funding 与 OI 联合信号（时间修复版）",
            ResearchStatus.REJECTED,
            False,
            "修正 OI 实际可用时间后，形成期 4h 净收益为负且跨币种不一致。",
            (
                "docs/funding_oi_trend_confirmation_repaired_2026-07-12.md",
                "reports/funding_oi_trend_confirmation_repaired.json",
            ),
        ),
        ResearchRecord(
            "range_regime_funding_extreme",
            "震荡行情内 Funding 异常",
            ResearchStatus.REJECTED,
            False,
            "形成期 4h 均值回复净收益为负、胜率低于 55%，且月度事件集中度超过 30%。",
            (
                "docs/funding_extreme_range_regime_design_review_2026-07-12.md",
                "docs/range_regime_funding_extreme_audit_2026-07-12.md",
                "reports/range_regime_funding_extreme_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_oi_independent_change",
            "日线 OI 独立变化率",
            ResearchStatus.REJECTED,
            False,
            "形成期 4h 最佳方向胜率低于 55%，样本外 4h 两侧扣成本后均为负。",
            (
                "docs/daily_oi_independent_change_research_card.md",
                "docs/daily_oi_independent_change_audit_2026-07-12.md",
                "reports/daily_oi_independent_change_audit.json",
            ),
        ),
        ResearchRecord(
            "donchian_atr_trend_baseline",
            "唐奇安通道 + ATR 趋势基准",
            ResearchStatus.REJECTED,
            False,
            "形成期单月事件集中度超过预注册上限，样本外扣成本后净均值为负。",
            (
                "docs/strategy_universe_and_research_priorities_2026-07-12.md",
                "docs/donchian_atr_trend_baseline_research_card.md",
                "docs/donchian_atr_trend_baseline_audit_2026-07-12.md",
                "docs/donchian_atr_trend_baseline_regime_conditioned_audit_2026-07-13.md",
                "reports/donchian_atr_trend_baseline_audit.json",
                "reports/donchian_atr_trend_baseline_regime_conditioned_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_low_turnover_momentum",
            "日线低换手 90 日动量",
            ResearchStatus.REJECTED,
            False,
            "形成期事件数不足且收益集中，样本外扣成本后净收益为负。",
            (
                "docs/daily_low_turnover_momentum_audit_2026-07-12.md",
                "reports/daily_low_turnover_momentum_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_ma_alignment",
            "日线均线多头排列趋势",
            ResearchStatus.REJECTED,
            False,
            "形成期只有 3 笔事件、样本外没有新入场事件，且正收益贡献高度集中。",
            (
                "docs/daily_ma_alignment_audit_2026-07-13.md",
                "reports/daily_ma_alignment_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_bb_mean_revert",
            "日线布林带均值回复",
            ResearchStatus.REJECTED,
            False,
            "形成期与样本外均为正，但样本外单月正收益贡献占比 63.49%，超过集中度上限。",
            (
                "docs/daily_bb_mean_revert_audit_2026-07-13.md",
                "docs/daily_bb_mean_revert_regime_conditioned_audit_2026-07-13.md",
                "reports/daily_bb_mean_revert_audit.json",
                "reports/daily_bb_mean_revert_regime_conditioned_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_rsi_mean_revert",
            "日线 RSI 均值回复",
            ResearchStatus.REJECTED,
            False,
            "裸事件形成期与样本外为正，但按震荡适配标签过滤后没有合格事件，不能作为震荡方向腿。",
            (
                "docs/daily_rsi_mean_revert_audit_2026-07-13.md",
                "docs/daily_rsi_mean_revert_regime_conditioned_audit_2026-07-13.md",
                "docs/daily_rsi_downtrend_rebound_regime_conditioned_audit_2026-07-13.md",
                "docs/directional_regime_event_inventory_2026-07-13.md",
                "reports/daily_rsi_mean_revert_audit.json",
                "reports/daily_rsi_mean_revert_regime_conditioned_audit.json",
                "reports/daily_rsi_downtrend_rebound_regime_conditioned_audit.json",
                "reports/directional_regime_event_inventory.json",
            ),
        ),
        ResearchRecord(
            "daily_trend_pullback",
            "日线趋势内回调",
            ResearchStatus.REJECTED,
            False,
            "裸事件形成期与样本外均为负；按上行趋势适配标签过滤后样本外均值仍为负。",
            (
                "docs/daily_trend_pullback_audit_2026-07-13.md",
                "docs/daily_trend_pullback_regime_conditioned_audit_2026-07-13.md",
                "reports/daily_trend_pullback_audit.json",
                "reports/daily_trend_pullback_regime_conditioned_audit.json",
            ),
        ),
        ResearchRecord(
            "4h_ema_crossover",
            "4 小时 EMA20/50 交叉",
            ResearchStatus.REJECTED,
            False,
            "裸跑样本外失败；按完成 4h 行情标签过滤后，OOS 趋势适配桶为正，可作为需 regime gate 的条件型方向弱信号继续研究。",
            (
                "docs/ema_crossover_4h_research_card.md",
                "docs/ema_crossover_4h_audit_2026-07-13.md",
                "docs/ema_crossover_4h_regime_conditioned_audit_2026-07-13.md",
                "reports/ema_crossover_4h_audit.json",
                "reports/ema_crossover_4h_regime_conditioned_audit.json",
            ),
        ),
        ResearchRecord(
            "range_regime_mean_reversion_family",
            "震荡行情内均值回归家族",
            ResearchStatus.REJECTED,
            False,
            "形成期扣成本后净均值为负、胜率低于 55%，且盈利因子低于 1.2。",
            (
                "docs/strategy_universe_and_research_priorities_2026-07-12.md",
                "docs/range_regime_mean_reversion_research_card.md",
                "docs/range_regime_mean_reversion_audit_2026-07-12.md",
                "reports/range_regime_mean_reversion_audit.json",
            ),
        ),
        ResearchRecord(
            "utc_session_breakout_family",
            "UTC 时段开盘区间突破家族",
            ResearchStatus.REJECTED,
            False,
            "形成期扣成本后净均值为负、胜率低于 45%，且盈利因子低于 1.2。",
            (
                "docs/strategy_universe_and_research_priorities_2026-07-12.md",
                "docs/utc_session_breakout_research_card.md",
                "docs/utc_session_breakout_audit_2026-07-12.md",
                "reports/utc_session_breakout_audit.json",
            ),
        ),
        ResearchRecord(
            "okx_futures_calendar_spread",
            "OKX 交割合约跨期价差",
            ResearchStatus.REJECTED,
            False,
            "真实覆盖审计通过，但预注册均值回归规则在形成期和样本外扣除 0.32% 四腿成本后均失败。",
            (
                "docs/strategy_universe_and_research_priorities_2026-07-12.md",
                "docs/okx_futures_calendar_spread_data_feasibility_2026-07-12.md",
                "docs/okx_futures_calendar_spread_pipeline_research_card.md",
                "docs/okx_futures_calendar_spread_pipeline_implementation_2026-07-12.md",
                "docs/okx_futures_historical_data_downloader_implementation_2026-07-12.md",
                "docs/okx_futures_calendar_spread_coverage_audit_implementation_2026-07-12.md",
                "docs/okx_futures_calendar_spread_real_coverage_2026-07-12.md",
                "docs/okx_futures_calendar_spread_series_and_descriptive_audit_2026-07-12.md",
                "docs/okx_futures_calendar_spread_mean_reversion_research_card.md",
                "docs/okx_futures_calendar_spread_mean_reversion_audit_2026-07-12.md",
                "reports/okx_futures_calendar_spread_coverage_audit_202506_202606.json",
                "reports/okx_futures_calendar_spread_descriptive_audit.json",
                "reports/okx_futures_calendar_spread_mean_reversion_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_williams_r_range_reversion",
            "日线 Williams %R 震荡反转",
            ResearchStatus.REJECTED,
            False,
            "形成期与样本外扣除成本后均为负，且月度集中度分别为 41.07% 与 37.10%。",
            (
                "docs/daily_williams_r_range_reversion_audit_result_2026-07-15.md",
                "reports/daily_williams_r_range_reversion_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_parabolic_sar_trend",
            "日线 Parabolic SAR 趋势",
            ResearchStatus.REJECTED,
            False,
            "形成期净均值为负；样本外虽为正，但月度集中度 32.13% 超过上限。",
            (
                "docs/daily_parabolic_sar_trend_audit_result_2026-07-15.md",
                "reports/daily_parabolic_sar_trend_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_atr_expansion_breakout",
            "日线 ATR 放大突破",
            ResearchStatus.REJECTED,
            False,
            "形成期收益高度集中于单月，样本外扣除成本后显著为负。",
            (
                "docs/daily_atr_expansion_breakout_audit_result_2026-07-15.md",
                "reports/daily_atr_expansion_breakout_audit.json",
            ),
        ),
        ResearchRecord(
            "daily_volume_confirmed_breakout",
            "日线成交量确认突破",
            ResearchStatus.REJECTED,
            False,
            "形成期和样本外均为负，胜率低且正收益高度集中。",
            (
                "docs/daily_volume_confirmed_breakout_audit_result_2026-07-15.md",
                "reports/daily_volume_confirmed_breakout_audit.json",
            ),
        ),
        ResearchRecord(
            "regime_component_shared_capital_combo",
            "四袖套共享资金行情路由组合",
            ResearchStatus.REJECTED,
            False,
            "四个冻结袖套共享资金后累计收益 -64.39%、最大回撤 66.90%，五个半年窗口均为负。",
            (
                "docs/regime_component_walk_forward_audit_2026-07-15.md",
                "reports/regime_component_walk_forward_audit.json",
            ),
        ),
        ResearchRecord(
            "grid_martingale_locking_family",
            "网格、马丁与锁仓加仓家族",
            ResearchStatus.RISK_BLOCKED,
            False,
            "默认冻结；这类 EA 容易用尾部风险换取平滑收益，违反当前不得制造表面收益的研究约束。",
            ("docs/strategy_universe_and_research_priorities_2026-07-12.md",),
        ),
        ResearchRecord(
            "ml_dynamic_router_family",
            "机器学习与动态路由家族",
            ResearchStatus.FROZEN,
            False,
            "冻结为组合器/分类器方向；在没有独立、已批准 alpha 前不得用模型调参制造交易信号。",
            ("docs/strategy_universe_and_research_priorities_2026-07-12.md",),
        ),
        ResearchRecord(
            "external_event_news_macro_family",
            "外部事件、新闻舆情与宏观方向",
            ResearchStatus.FROZEN,
            False,
            "缺少免费公开可复现的 365 天结构化历史事件数据，发布时间对齐和前视偏差风险过高。",
            (
                "docs/strategy_universe_and_research_priorities_2026-07-12.md",
                "docs/external_event_news_macro_freeze_2026-07-12.md",
            ),
        ),
    )


def build_registry() -> dict[str, object]:
    items = [asdict(record) for record in records()]
    approved = [item["research_id"] for item in items if item["status"] == ResearchStatus.APPROVED]
    paper_eligible = [item["research_id"] for item in items if item["eligible_for_paper"]]
    status_counts: dict[str, int] = {}
    for item in items:
        raw_status = item["status"]
        status = raw_status.value if isinstance(raw_status, ResearchStatus) else str(raw_status)
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "approval_rule": "Only records explicitly approved and paper-eligible may enter paper trading.",
        "records": items,
        "status_counts": status_counts,
        "approved_for_paper": paper_eligible,
        "approved_research": approved,
        "safe_to_enable_trading": bool(paper_eligible),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the research approval registry.")
    parser.add_argument("--out", type=Path, default=Path("reports/research_approval_registry.json"))
    args = parser.parse_args(argv)
    payload = build_registry()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
