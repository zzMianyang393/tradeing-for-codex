# 研究报告索引（2026-07-12）

## 注册状态总览

- **approved = 0**
- **candidate = 0**
- rejected = 19
- invalid = 2
- risk_blocked = 1
- frozen = 2
- meta_only = 10
- approved_for_paper = []
- safe_to_enable_trading = false

---

## rejected（已淘汰）

| # | 研究 ID | 中文名 | 核心结论 | 证据路径 |
|---|---|---|---|---|
| 1 | relative_strength_persistence | 相对强弱持续 | 365d -0.91%，35.8% WR，全窗口亏损 | `reports/rs_persistence_entry_timing_audit.json` |
| 2 | btc_trend_pullback | BTC 趋势内山寨币回调 | 形成期 -7.36%，趋势上行情 -0.77% | `reports/btc_trend_pullback_regime_formation.json` |
| 3 | vol_compression_breakout | 波动率压缩突破 | 形成期样本不足，方向矛盾 | `reports/vol_compression_breakout_entry_timing_audit.json` |
| 4 | pairs_walk_forward | 配对严格交易 | 406 对 FDR 后 0 对通过 | `reports/pairs_walk_forward_v1.json` |
| 5 | spot_perp_basis | 期现基差套利 | 95 分位 +2.1bp vs 成本 28bp | `reports/okx_basis_audit.json`, `reports/basis_microstructure_audit.json` |
| 6 | multi_coin_funding_crowding | 多币种 funding 拥挤反转 | 46 事件，-0.28%，不足以覆盖成本 | `reports/multi_coin_funding_crowding_audit.json` |
| 7 | btc_alt_lead_lag | BTC→山寨币短时领先滞后 | 2368 事件，成本后 -0.23%，WR 37.7% | `reports/btc_alt_lead_lag_formation.json` |
| 8 | positive_funding_carry | 正 funding 市场中性持有 | BTC/ETH 形成期 0 个满足成本事件 | `reports/funding_carry_formation.json` |
| 9 | funding_term_carry | 中周期 Funding Term Carry | 14 天 funding 收入不足以覆盖四腿成本，形成期与 OOS 均为负 | `reports/funding_term_carry_audit.json` |
| 10 | funding_oi_time_corrected | Funding+OI 趋势确认（修正后） | 形成期 4h -0.04%，WR 47.8%，OOS -0.15% | `reports/funding_oi_trend_confirmation_repaired.json` |
| 11 | range_regime_funding_extreme | 震荡行情内 funding 异常 | 321 事件，4h -0.13%，WR 43.3%，月集中 36.4% | `reports/range_regime_funding_extreme_audit.json` |
| 12 | daily_oi_independent_change | 日度 OI 独立变化信号 | 事件不足或净收益为负 | — |
| 13 | donchian_atr_trend_baseline | 唐奇安+ATR 趋势基准 | 形成期净收益为负，WR 不足 | `reports/donchian_atr_trend_baseline_audit.json` |
| 14 | daily_low_turnover_momentum | 日线低换手 90 日动量 | 形成期事件不足且收益集中，样本外净收益为负 | `reports/daily_low_turnover_momentum_audit.json` |
| 15 | daily_ma_alignment | 日线均线多头排列趋势 | 形成期仅 3 事件，OOS 无新入场事件，收益贡献高度集中 | `reports/daily_ma_alignment_audit.json` |
| 16 | daily_bb_mean_revert | 日线布林带均值回复 | 形成期与 OOS 为正，但 OOS 单月正收益贡献 63.49%，集中度超标 | `reports/daily_bb_mean_revert_audit.json` |
| 17 | range_regime_mean_reversion_family | 震荡内均值回归家族 | 形成期净收益为负 | `reports/range_regime_mean_reversion_audit.json` |
| 18 | utc_session_breakout_family | UTC 时段突破家族 | 形成期净收益为负 | `reports/utc_session_breakout_audit.json` |
| 19 | okx_futures_calendar_spread | OKX 交割合约跨期价差 | 形成期净收益为负 | `reports/okx_futures_calendar_spread_mean_reversion_audit.json` |

## invalid（数据/时序无效）

| # | 研究 ID | 中文名 | 核心结论 | 证据路径 |
|---|---|---|---|---|
| 1 | legacy_dynamic_router | 旧动态路由策略 | MFE 标签、旧路由、时间语义问题 | `docs/research_decision_2026-07-10.md` |
| 2 | funding_oi_joint_original | Funding+OI 联合（原始版） | 前视偏差：00:00 入场使用 16:00 数据 | `reports/funding_oi_joint_audit.json` |

## risk_blocked（风险阻断）

| # | 研究 ID | 中文名 | 核心结论 | 证据路径 |
|---|---|---|---|---|
| 1 | grid_martingale_locking_family | 网格/马丁/锁仓家族 | 策略类型禁止：无限亏损风险 | — |

## frozen（数据不足冻结）

| # | 研究 ID | 中文名 | 核心结论 | 证据路径 |
|---|---|---|---|---|
| 1 | ml_dynamic_router_family | ML 动态路由家族 | 免费数据不足，需付费 OI/订单流 | — |
| 2 | external_event_news_macro_family | 外部事件/新闻/宏观 | 免费可复现历史数据不足 | `docs/external_event_news_macro_freeze_2026-07-12.md` |

## meta_only（元研究/框架）

| # | 研究 ID | 中文名 | 核心结论 | 证据路径 |
|---|---|---|---|---|
| 1 | cross_time_stability | 跨时间稳定性元审计 | 17 稳定 / 7 不稳定 / 0 样本不足 | `reports/cross_time_stability_audit.json` |
| 2 | execution_cost_floor | 执行成本底线审计 | 确认单市场 0.16%、四腿 0.32% 往返成本地板 | `reports/execution_cost_floor_audit.json` |
| 3 | low_turnover_research_gate | 低换手研究准入门 | 每月 ≤12 事件，持有 ≥3 天 | `reports/low_turnover_research_gate.json` |
| 4 | no_trade_filter_research | 不交易过滤器候选元审计 | 从已淘汰报告提取禁交易状态候选，证据有限 | `reports/no_trade_filter_research.json` |
| 5 | okx_free_data_liquidity_map | OKX 免费数据覆盖与流动性地图 | 约束可研究数据范围与流动性分层 | `docs/okx_free_data_liquidity_map_2026-07-12.md` |
| 6 | rejected_strategy_failure_clusters | 已淘汰策略失败原因聚类 | 聚类 15 个 rejected 的失败原因，防止换壳重跑 | `docs/rejected_strategy_failure_clusters_2026-07-12.md` |
| 7 | frozen_family_reactivation_criteria | 冻结家族长期重启条件 | 约束 frozen/risk_blocked 家族未来重启条件 | `docs/frozen_family_reactivation_criteria_2026-07-12.md` |
| 8 | low_turnover_public_research_scan | 低换手公开研究方向扫描 | 仅扫描未注册低换手方向，不批准 candidate | `docs/low_turnover_public_research_scan_2026-07-12.md` |
| 9 | oi_deleveraging_filter | OI 去杠杆过滤器元审计 | 可作为高杠杆风险状态标签，不得作为策略或硬过滤器 | `reports/oi_deleveraging_filter_audit.json` |
| 10 | research_risk_map | 研究风险地图 | 聚合成本、换手、弱过滤器候选与 OI 风险状态，仅作研究前置闸门 | `reports/research_risk_map.json` |

---

## 无 approved 或 candidate 条目

本索引不包含任何 `approved` 或 `eligible_for_paper=true` 的条目。
