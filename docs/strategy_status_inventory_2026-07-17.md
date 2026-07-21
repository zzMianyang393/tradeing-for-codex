# 策略全景清单（历史研究注册表汇总）

生成：2026-07-17

- 条目数：**73**
- 任一 `eligible_for_paper`：**False**
- 状态计数：`{'invalid': 2, 'rejected': 27, 'meta_only': 10, 'risk_blocked': 1, 'frozen': 2, 'historical_rejected': 4, 'legacy_limited_scope_evidence': 1, 'insufficient_evidence': 6, 'requires_specification': 1, 'observation_only': 1, 'frozen_awaiting_prospective': 1, 'watchlist_concentration_risk': 2, 'combo_watchlist_strict_gate_failed': 2, 'posthoc_directional_weak_feature_watchlist': 1, 'prospective_pair_comparison_only': 6, 'posthoc_sleeve_weak_feature_watchlist': 1, 'posthoc_regime_sleeve_weak_feature_watchlist': 1, 'rejected_standalone_regime_gated_weak_feature_watchlist': 1, 'active_research_not_validated': 1, 'rejected_at_formation': 1, 'historical_walk_forward_rejected': 1}`
- 机器可读：`reports/prod/strategy_status_inventory.json`

## 总结论

**没有任何策略获准模拟盘或实盘。** 下表「历史收益」来自旧报告/观察字段，不等于可交易 edge；很多高收益是集中度/短窗/污染样本。

### 失败原因类型（读表时对照）

| 类型 | 含义 |
|------|------|
| rejected / historical_rejected | 按预注册闸门失败或样本外失效 |
| invalid | 方法错误/标签污染/不可当证据 |
| risk_blocked | 风险结构禁止（网格/马丁等） |
| insufficient_evidence | 样本/稳定性不够，不判过 |
| frozen_awaiting_prospective | 历史好看但未前瞻证明 |
| watchlist_* / concentration | 有正贡献但过度集中或事后挑选 |
| combo_*_failed | 组合严格闸门未过 |
| active_research_not_validated | 在研未验证（如 10U v2） |

## rejected（27）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `4h_ema_crossover` | 4 小时 EMA20/50 交叉 | （无解析数字） | 裸跑样本外失败；按完成 4h 行情标签过滤后，OOS 趋势适配桶为正，可作为需 regime gate 的条件型方向弱信号继续研究。 |
| `btc_alt_lead_lag` | BTC 对非 BTC 短时领先滞后 | （无解析数字） | 形成期成本前后均为负。 |
| `btc_trend_pullback` | BTC 趋势内山寨回调 | （无解析数字） | 形成期整体亏损，理论适用的趋势上行标签同样为负。 |
| `daily_atr_expansion_breakout` | 日线 ATR 放大突破 | （无解析数字） | 形成期收益高度集中于单月，样本外扣除成本后显著为负。 |
| `daily_bb_mean_revert` | 日线布林带均值回复 | （无解析数字） | 形成期与样本外均为正，但样本外单月正收益贡献占比 63.49%，超过集中度上限。 |
| `daily_low_turnover_momentum` | 日线低换手 90 日动量 | （无解析数字） | 形成期事件数不足且收益集中，样本外扣成本后净收益为负。 |
| `daily_ma_alignment` | 日线均线多头排列趋势 | （无解析数字） | 形成期只有 3 笔事件、样本外没有新入场事件，且正收益贡献高度集中。 |
| `daily_oi_independent_change` | 日线 OI 独立变化率 | （无解析数字） | 形成期 4h 最佳方向胜率低于 55%，样本外 4h 两侧扣成本后均为负。 |
| `daily_parabolic_sar_trend` | 日线 Parabolic SAR 趋势 | （无解析数字） | 形成期净均值为负；样本外虽为正，但月度集中度 32.13% 超过上限。 |
| `daily_rsi_mean_revert` | 日线 RSI 均值回复 | （无解析数字） | 裸事件形成期与样本外为正，但按震荡适配标签过滤后没有合格事件，不能作为震荡方向腿。 |
| `daily_trend_pullback` | 日线趋势内回调 | （无解析数字） | 裸事件形成期与样本外均为负；按上行趋势适配标签过滤后样本外均值仍为负。 |
| `daily_volume_confirmed_breakout` | 日线成交量确认突破 | （无解析数字） | 形成期和样本外均为负，胜率低且正收益高度集中。 |
| `daily_williams_r_range_reversion` | 日线 Williams %R 震荡反转 | （无解析数字） | 形成期与样本外扣除成本后均为负，且月度集中度分别为 41.07% 与 37.10%。 |
| `donchian_atr_trend_baseline` | 唐奇安通道 + ATR 趋势基准 | （无解析数字） | 形成期单月事件集中度超过预注册上限，样本外扣成本后净均值为负。 |
| `funding_oi_time_corrected` | Funding 与 OI 联合信号（时间修复版） | （无解析数字） | 修正 OI 实际可用时间后，形成期 4h 净收益为负且跨币种不一致。 |
| `funding_term_carry` | 中周期 Funding Term Carry | （无解析数字） | 14 天 funding 收入均值不足以覆盖 0.32% 四腿往返成本，形成期与样本外净均值均为负。 |
| `multi_coin_funding_crowding` | 多币种资金费率拥挤反转 | （无解析数字） | 事件收益为负且无法覆盖成本。 |
| `okx_futures_calendar_spread` | OKX 交割合约跨期价差 | （无解析数字） | 真实覆盖审计通过，但预注册均值回归规则在形成期和样本外扣除 0.32% 四腿成本后均失败。 |
| `pairs_walk_forward` | 配对统计套利 | （无解析数字） | 无配对通过严格形成期、样本外和多重检验门槛。 |
| `positive_funding_carry` | 正资金费率市场中性持有 | （无解析数字） | 形成期没有足以覆盖四腿成本的合格事件。 |
| `range_regime_funding_extreme` | 震荡行情内 Funding 异常 | （无解析数字） | 形成期 4h 均值回复净收益为负、胜率低于 55%，且月度事件集中度超过 30%。 |
| `range_regime_mean_reversion_family` | 震荡行情内均值回归家族 | （无解析数字） | 形成期扣成本后净均值为负、胜率低于 55%，且盈利因子低于 1.2。 |
| `regime_component_shared_capital_combo` | 四袖套共享资金行情路由组合 | （无解析数字） | 四个冻结袖套共享资金后累计收益 -64.39%、最大回撤 66.90%，五个半年窗口均为负。 |
| `relative_strength_persistence` | 相对强弱持续 | （无解析数字） | 样本外失败，高延伸追强组入场质量更差。 |
| `spot_perp_basis` | 期现基差套利 | （无解析数字） | 基差幅度不足以覆盖完整四腿成本。 |
| `utc_session_breakout_family` | UTC 时段开盘区间突破家族 | （无解析数字） | 形成期扣成本后净均值为负、胜率低于 45%，且盈利因子低于 1.2。 |
| `vol_compression_breakout` | 波动率压缩突破 | （无解析数字） | 样本不足且完整验证失败。 |

## historical_rejected（4）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `MR_14` | BTC 趋势领先山寨动量 | （无解析数字） | priority_queue; source=btc_trend_confirmed_alt_momentum_audit.json |
| `TF_06` | 自适应卡夫曼均线 (KAMA) 趋势 | （无解析数字） | priority_queue; source=daily_kama_trend_audit.json |
| `TF_08` | 超趋势指标 (SuperTrend) 跟踪 | （无解析数字） | priority_queue; source=daily_supertrend_audit.json |
| `TF_09` | 价格斜率与动量回归通道 | （无解析数字） | priority_queue; source=daily_regression_channel_trend_audit.json |

## rejected_at_formation（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `ten_u_trend_breakout_v1` | 10U Warlord 趋势突破 v1 | ret≈-41.12% | Formation -41.12% PF 0.87 across 123 trades; validation sealed |

## invalid（2）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `funding_oi_joint_original` | Funding 与 OI 联合信号（原始报告） | （无解析数字） | 将当天完整 funding 与日线 OI 用于当天 00:00 入场，存在前视偏差。 |
| `legacy_dynamic_router` | 旧动态路由高收益报告 | （无解析数字） | 旧配置、路由复用与 MFE 标签问题使历史高收益不可作为策略证据。 |

## risk_blocked（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `grid_martingale_locking_family` | 网格、马丁与锁仓加仓家族 | （无解析数字） | 默认冻结；这类 EA 容易用尾部风险换取平滑收益，违反当前不得制造表面收益的研究约束。 |

## historical_walk_forward_rejected（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `historical_four_sleeve_shared_capital_combo` | 四袖套共享资金组合基线 | ret≈-64.39%, DD≈66.90% | WF return ~-64.4% maxDD ~66.9%; 0/5 positive half-year windows; sealed diagnostic |

## frozen（2）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `external_event_news_macro_family` | 外部事件、新闻舆情与宏观方向 | （无解析数字） | 缺少免费公开可复现的 365 天结构化历史事件数据，发布时间对齐和前视偏差风险过高。 |
| `ml_dynamic_router_family` | 机器学习与动态路由家族 | （无解析数字） | 冻结为组合器/分类器方向；在没有独立、已批准 alpha 前不得用模型调参制造交易信号。 |

## frozen_awaiting_prospective（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `low_volatility_drift_bb_breakout_fixed_risk_v1` |  | ret≈64.45%, DD≈17.29% | hist_ret%=64.447086 maxDD%=17.2916 positions=787 prospective_start=2026-07-11 |

## meta_only（10）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `cross_time_stability` | 跨时间稳定性元审计 | （无解析数字） | 用于约束数据和研究设计，不产生开仓信号。 |
| `execution_cost_floor` | 执行成本地板元审计 | （无解析数字） | 用于约束未来研究的最低毛收益门槛，不产生开仓信号。 |
| `frozen_family_reactivation_criteria` | 冻结家族长期重启条件 | （无解析数字） | 用于约束冻结或风险受阻家族的未来重启条件，不产生开仓信号。 |
| `low_turnover_public_research_scan` | 低换手公开研究方向扫描 | （无解析数字） | 仅扫描未注册低换手研究方向，不批准候选策略或开仓信号。 |
| `low_turnover_research_gate` | 低换手研究门槛元审计 | （无解析数字） | 用于阻止未来研究回到高换手小边际参数搜索，不产生开仓信号。 |
| `no_trade_filter_research` | 不交易过滤器候选元审计 | （无解析数字） | 用于从已淘汰报告中提取未来禁交易状态候选，样本有限且不产生开仓或过滤执行规则。 |
| `oi_deleveraging_filter` | OI 去杠杆过滤器元审计 | （无解析数字） | 用于识别高 OIVR 杠杆风险状态；不得作为开仓策略或硬性禁交易过滤器。 |
| `okx_free_data_liquidity_map` | OKX 免费数据覆盖与流动性地图 | （无解析数字） | 用于约束可研究数据范围和流动性分层，不产生开仓信号。 |
| `rejected_strategy_failure_clusters` | 已淘汰策略失败原因聚类 | （无解析数字） | 用于归纳已拒绝策略失败原因，防止换壳重跑，不产生开仓信号。 |
| `research_risk_map` | 研究风险地图 | （无解析数字） | 聚合成本、换手、弱过滤器候选与 OI 风险状态；仅作为研究前置闸门，不产生交易信号。 |

## insufficient_evidence（6）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `MR_03` | RSI 日线超卖分位数反转 | （无解析数字） | priority_queue; source=daily_rsi_percentile_range_reversion_audit.json |
| `MR_06` | 乖离率 (BIAS) 偏离度反转 | （无解析数字） | priority_queue; source=daily_bias_range_reversion_audit.json |
| `MR_07` | 价格偏离度 (Z-Score) 极端回复 | （无解析数字） | priority_queue; source=daily_zscore_range_reversion_audit.json |
| `TS_02` | 周末低流动性均值回复 | （无解析数字） | priority_queue; source=weekend_low_liquidity_reversion_audit.json |
| `TS_07` | 月度首尾资金注入效应 | （无解析数字） | priority_queue; source=month_boundary_flow_audit.json |
| `VS_06` | Parkinson 极值波动率均值回复 | （无解析数字） | priority_queue; source=parkinson_volatility_extreme_reversion_audit.json |

## legacy_limited_scope_evidence（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `MR_02` | 日线级别布林带边界回归 | （无解析数字） | priority_queue; source=daily_bb_mean_revert_audit.json |

## observation_only（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `VS_05` | 日内极差自适应波动率扩展 | （无解析数字） | priority_queue; source=daily_volatility_expansion_continuation_audit.json |

## requires_specification（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `MR_09` | 价格中枢引力通道 (Demux) | （无解析数字） | priority_queue; source=None |

## active_research_not_validated（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `ten_u_single_symbol_persistent_event_trend_48h_v2` | 10U 战神 Event Trend v2 | ret≈1950.06%, DD≈18.74% (sealed 45d 3 trades 10->205; informal full ~23 trades ~209) | sealed_screen_insufficient_evidence (3 trades); dominated by RAVE; prod paper-prep only; not live-authorized |

## watchlist_concentration_risk（2）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `ema_continuation_short_downtrend_v1` |  | +10.256000% contribution, 43.16% positive-month concentration | positive future contribution but component concentration exceeds 25% |
| `persistent_uptrend_ema20_reclaim_v1` |  | +4.697309% observed return, 37.97% positive-month concentration | primary BTC/ETH panel passes core weak-feature checks but positive-month concentration exceeds 25% |

## posthoc_directional_weak_feature_watchlist（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `daily_volume_shock_reversal_v1_short` |  | +9.376166% observed return, 11.839900% max DD | short side was discovered after the frozen bidirectional rule failed on its long side |

## posthoc_sleeve_weak_feature_watchlist（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `weekly_cross_sectional_momentum_v1_short` |  | +76.810624% observed return, 14.434100% max DD | short sleeve was discovered after the frozen weekly long-short rule failed on its long sleeve |

## posthoc_regime_sleeve_weak_feature_watchlist（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `weekly_range_microtrend_continuation_v1_long` |  | +2.034988% observed return, 2.891700% max DD | long sleeve was discovered after the frozen bidirectional range rule failed its fold gate |

## combo_watchlist_strict_gate_failed（2）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `combo::low_volatility_drift_bb_breakout_fixed_risk_v1__persistent_uptrend_ema20_reclaim_v1` |  | +68.241452% observed return, 17.378600% max DD, +0.087000pp DD excess | retained post-hoc for risk-adjusted observation but failed the pre-registered absolute drawdown gate |
| `combo::persistent_uptrend_ema20_reclaim_v1__ema_continuation_short_downtrend_v1` |  | +16.121283% observed return, 8.951700% max DD, +0.531800pp DD excess | retained post-hoc for risk-adjusted observation but failed the pre-registered absolute drawdown gate |

## prospective_pair_comparison_only（6）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `pair_watchlist::daily_volume_shock_reversal_v1_short__ema_continuation_short_downtrend_v1` |  | complementarity gate passed; historical combo simulation prohibited | pair is complementary but contains a post-hoc directional feature |
| `pair_watchlist::daily_volume_shock_reversal_v1_short__persistent_uptrend_ema20_reclaim_v1` |  | complementarity gate passed; historical combo simulation prohibited | pair is complementary but contains a post-hoc directional feature |
| `pair_watchlist::weekly_cross_sectional_momentum_v1_short__persistent_uptrend_ema20_reclaim_v1` |  | complementarity gate passed; historical combo simulation prohibited | pair is complementary but contains a post-hoc weekly short sleeve |
| `pair_watchlist::weekly_range_microtrend_continuation_v1_long__daily_volume_shock_reversal_v1_short` |  | complementarity gate passed; historical combo simulation prohibited | pair is complementary but contains a post-hoc range-regime long sleeve |
| `pair_watchlist::weekly_range_microtrend_continuation_v1_long__ema_continuation_short_downtrend_v1` |  | complementarity gate passed; historical combo simulation prohibited | pair is complementary but contains a post-hoc range-regime long sleeve |
| `pair_watchlist::weekly_range_microtrend_continuation_v1_long__persistent_uptrend_ema20_reclaim_v1` |  | complementarity gate passed; historical combo simulation prohibited | pair is complementary but contains a post-hoc range-regime long sleeve |

## rejected_standalone_regime_gated_weak_feature_watchlist（1）

| ID | 名称 | 历史收益线索 | 为何不通过 / 状态说明 |
|----|------|--------------|----------------------|
| `donchian_atr_trend_baseline` |  | 1 unique regime-compatible prospective signal; standalone status remai | rejected standalone rule is reused only as a regime-gated weak signal per the combination policy |

