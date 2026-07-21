# 研究状态总览（2026-07-16）

## 一句话状态

**没有任何策略获准模拟盘或实盘。所有安全闸门关闭。**

---

## 111 原型宇宙

| 状态 | 数量 |
|---|---|
| data_blocked | 10 |
| duplicate_rejected | 23 |
| eligible_for_research | 52 |
| frozen | 2 |
| meta_only | 17 |
| risk_blocked | 7 |
| **合计** | **111** |

## 结构优先候选（research_card_priority）

数量：**13**

这些原型通过了单腿、低换手、OHLCV-only、免费可复现、无已淘汰家族重叠的筛选。
获得研究卡不等于获批交易。当前已关闭：**13**；开放历史回测：**0**。
- 队列结论：`historical_priority_queue_closed_preserve_prospective_cohorts`

## Cohort A（已密封）

- 信号数：28
- 共同截止点：2026-07-13 08:15:00
- 已到期：0
- 未到期：28
- 密封结果评估：awaiting_maturity（已评估：False）
- 同标的同时间多因子事件：1
- 共现信号占比：7.14%
- 共现审计只描述结构重叠，不构成组合收益或交易资格证据。

## 组合特征池（研究层）

- 特征数：42
- 方向弱信号：6
- 环境标签：18
- 风险过滤候选：6
- 硬阻断：12
- 校验违规：0
- 组合回测资格：False。

## Cohort B（活跃）

- 信号数：1
- 共同截止点：2026-07-16 03:30:00
- 已准入假设：daily_rsi_downtrend_rebound_v1, daily_volatility_expansion_continuation_v1, daily_failed_breakout_reversal_v1

## 组合观察（仅信号元数据）

- 原始 / 去重信号：28 / 23
- 严格同向共识：1
- 反向冲突锁定：4
- 24h 同向 / 反向交互：3 / 5
- 仅描述共现和冲突；未评估价格、收益或结果，不能进入组合回测。

## 历史组合基线

- 四袖套共享资金：`historical_walk_forward_rejected`
- 事件 / 接受仓位：2607 / 1043
- 收益 / 最大回撤：-64.392729% / 66.8995%
- 正收益半年窗口：0/5
- 诊断封存：`sealed`
- 该基线已淘汰，不能作为组合候选或权重优化起点。
- 留一袖套剔除仅用于失败归因，所有结果均不是候选。
- 冻结趋势弱因子袖套：`historical_combo_diagnostic_rejected`；OOS 收益 / 最大回撤：-6.141369% / 14.9181%。
- 趋势袖套同样已淘汰；仅保留为组合失败证据，不可用于权重优化。

## Cohort C（前瞻探索）

- 假设：daily_volatility_expansion_short_exploration_v1
- 激活边界：2026-07-16 00:00:00
- 数据截止点：2026-07-16 03:30:00
- 覆盖状态：active
- 信号数：0
- 最新刷新：no_changes（正式提交：False）
- 密封评估预检：awaiting_first_published_observation（队列：0）
- 仅前瞻探索；不属于 Cohort B，不能构成历史批准。

## Cohort D（前瞻探索）

- 假设：weekly_cross_sectional_weakness_short_exploration_v1
- 激活边界：2026-07-20 00:00:00
- 数据截止点：2026-07-16 03:30:00
- 覆盖状态：awaiting_data_coverage
- 信号数：0
- 最新刷新：no_changes（正式提交：False）
- 密封评估预检：awaiting_first_published_observation（队列：0）
- 后验横截面弱势假设；独立于 Cohort B/C，不能构成历史批准。

## 活跃 Cohort 截止点对齐

- 状态：valid
- 数据质量截止点：2026-07-16 03:30:00
- B / C 截止点：2026-07-16 03:30:00 / 2026-07-16 03:30:00
- 问题数：0

## 历史审计

| 审计 | 状态 | 结论 |
|---|---|---|
| month_boundary_flow | audited | insufficient_evidence |
| weekend_low_liquidity_reversion | audited | insufficient_evidence |
| parkinson_volatility_extreme_reversion | audited | insufficient_evidence |
| daily_bias_range_reversion | audited | insufficient_evidence |
| daily_kdj_range_reversion | audited | insufficient_evidence |
| daily_spring_upthrust_range_reversion | audited | insufficient_evidence |
| daily_bb_squeeze_high_vol_breakout | audited | insufficient_evidence |
| weekly_cross_sectional_short_downtrend | audited | historical_rejected |

### 组合失败归因（诊断）

| 剔除袖套 | 收益 | 最大回撤 | 正收益半年窗口 | 仅诊断 |
|---|---:|---:|---:|---|
| uptrend_donchian_55_20_long | -74.377559% | 75.6873% | 0/5 | True |
| uptrend_supertrend_4h_long | -48.591635% | 58.7421% | 0/5 | True |
| range_bb_reversion_4h | -13.547889% | 45.0037% | 1/5 | True |
| range_rsi_reversion_4h | -58.36438% | 65.3016% | 0/5 | True |

## 安全闸门

- approved_for_paper: []
- eligible_for_paper: False
- safe_to_enable_trading: False
- ready_for_combo_backtest: False

## 状态分类

### historical_rejected (15)

- relative_strength_persistence
- btc_trend_pullback
- vol_compression_breakout
- pairs_walk_forward
- spot_perp_basis
- multi_coin_funding_crowding
- btc_alt_lead_lag
- positive_funding_carry
- funding_oi_time_corrected
- range_regime_funding_extreme
- donchian_atr_trend_baseline
- range_regime_mean_reversion_family
- utc_session_breakout_family
- okx_futures_calendar_spread
- daily_oi_independent_change

### insufficient_evidence (4)

- month_boundary_flow
- weekend_low_liquidity_reversion
- parkinson_volatility_extreme_reversion
- daily_bias_range_reversion

### prospective_active_with_signal (1)

- daily_rsi_downtrend_rebound_v1

### prospective_active_no_signal (2)

- daily_volatility_expansion_continuation_v1
- daily_failed_breakout_reversal_v1
