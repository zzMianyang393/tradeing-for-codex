# Canonical Strategy Account Replay

This measures only frozen daily event ledgers through one constrained account. It does not approve any strategy for paper or live trading.

| Strategy | Status | Formation | OOS | Aggregate | Max DD | Annualized Sharpe |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 日线 ATR 放大突破 (`daily_atr_expansion_breakout`) | `rejected` | +66.231% | -42.883% | -5.054% | +50.872% | +0.133 |
| 日线 BB 挤压高波动突破 (`daily_bb_squeeze_high_vol_breakout`) | `insufficient_evidence` | +1.944% | -1.449% | +0.466% | +11.313% | +0.149 |
| 日线 BIAS 震荡回归 (`daily_bias_range_reversion`) | `insufficient_evidence` | -3.301% | +0.000% | -3.301% | +3.301% | -53.057 |
| 日线 KAMA 趋势 (`daily_kama_trend`) | `historical_rejected` | +43.776% | -8.872% | +31.020% | +39.689% | +0.682 |
| 日线 Parabolic SAR 趋势 (`daily_parabolic_sar_trend`) | `rejected` | -16.195% | -12.241% | -26.445% | +40.525% | -0.347 |
| 日线回归通道趋势 (`daily_regression_channel_trend`) | `historical_rejected` | +47.441% | -24.093% | +11.918% | +35.607% | +0.401 |
| 日线 RSI 分位数震荡回归 (`daily_rsi_percentile_range_reversion`) | `insufficient_evidence` | +0.830% | +1.616% | +2.459% | +2.310% | +0.863 |
| 日线 Spring/Upthrust 反转 (`daily_spring_upthrust_range_reversion`) | `insufficient_evidence` | -1.121% | -0.883% | -1.994% | +7.645% | -0.153 |
| 日线趋势内回调 (`daily_trend_pullback`) | `rejected` | -2.624% | -27.966% | -29.857% | +37.648% | -0.556 |
| 日线成交量确认突破 (`daily_volume_confirmed_breakout`) | `rejected` | -10.374% | -8.023% | -17.565% | +27.468% | -0.370 |
| 日线 Williams %R 震荡反转 (`daily_williams_r_range_reversion`) | `rejected` | -21.317% | -17.570% | -35.141% | +37.488% | -1.160 |
| 日线 Z-score 震荡回归 (`daily_zscore_range_reversion`) | `insufficient_evidence` | +2.584% | +3.418% | +6.090% | +6.406% | +0.432 |

## Not Replayed

These records retain their historical status; the reason below is about measurement completeness, not a new trading decision.

| Strategy | Status | Reason |
| --- | --- | --- |
| 4 小时 EMA20/50 交叉 (`4h_ema_crossover`) | `rejected` | `not_daily_event_report` |
| BTC 对非 BTC 短时领先滞后 (`btc_alt_lead_lag`) | `rejected` | `not_daily_event_report` |
| BTC 趋势内山寨回调 (`btc_trend_pullback`) | `rejected` | `not_daily_event_report` |
| 跨时间稳定性元审计 (`cross_time_stability`) | `meta_only` | `not_daily_event_report` |
| 日线布林带均值回复 (`daily_bb_mean_revert`) | `rejected` | `events_missing_required_fields:direction` |
| 日线 KDJ 震荡回归 (`daily_kdj_range_reversion`) | `insufficient_evidence` | `no_event_ledger` |
| 日线低换手 90 日动量 (`daily_low_turnover_momentum`) | `rejected` | `not_daily_event_report` |
| 日线均线多头排列趋势 (`daily_ma_alignment`) | `rejected` | `not_daily_event_report` |
| 日线 OI 独立变化率 (`daily_oi_independent_change`) | `rejected` | `not_daily_event_report` |
| 日线 RSI 均值回复 (`daily_rsi_mean_revert`) | `rejected` | `events_missing_required_fields:direction` |
| 唐奇安通道 + ATR 趋势基准 (`donchian_atr_trend_baseline`) | `rejected` | `not_daily_event_report` |
| 执行成本地板元审计 (`execution_cost_floor`) | `meta_only` | `not_daily_event_report` |
| 外部事件、新闻舆情与宏观方向 (`external_event_news_macro_family`) | `frozen` | `missing_machine_readable_report` |
| 冻结家族长期重启条件 (`frozen_family_reactivation_criteria`) | `meta_only` | `missing_machine_readable_report` |
| 冻结趋势弱因子组合诊断 (`frozen_trend_weak_factor_sleeve`) | `historical_combo_diagnostic_rejected` | `not_daily_event_report` |
| Funding 与 OI 联合信号（原始报告） (`funding_oi_joint_original`) | `invalid` | `not_daily_event_report` |
| Funding 与 OI 联合信号（时间修复版） (`funding_oi_time_corrected`) | `rejected` | `not_daily_event_report` |
| 中周期 Funding Term Carry (`funding_term_carry`) | `rejected` | `not_daily_event_report` |
| 网格、马丁与锁仓加仓家族 (`grid_martingale_locking_family`) | `risk_blocked` | `missing_machine_readable_report` |
| 旧动态路由高收益报告 (`legacy_dynamic_router`) | `invalid` | `missing_machine_readable_report` |
| 低换手公开研究方向扫描 (`low_turnover_public_research_scan`) | `meta_only` | `missing_machine_readable_report` |
| 低换手研究门槛元审计 (`low_turnover_research_gate`) | `meta_only` | `not_daily_event_report` |
| 机器学习与动态路由家族 (`ml_dynamic_router_family`) | `frozen` | `missing_machine_readable_report` |
| 多币种资金费率拥挤反转 (`multi_coin_funding_crowding`) | `rejected` | `not_daily_event_report` |
| 不交易过滤器候选元审计 (`no_trade_filter_research`) | `meta_only` | `not_daily_event_report` |
| OI 去杠杆过滤器元审计 (`oi_deleveraging_filter`) | `meta_only` | `not_daily_event_report` |
| OKX 免费数据覆盖与流动性地图 (`okx_free_data_liquidity_map`) | `meta_only` | `missing_machine_readable_report` |
| OKX 交割合约跨期价差 (`okx_futures_calendar_spread`) | `rejected` | `not_daily_event_report` |
| 配对统计套利 (`pairs_walk_forward`) | `rejected` | `not_daily_event_report` |
| 正资金费率市场中性持有 (`positive_funding_carry`) | `rejected` | `not_daily_event_report` |
| 震荡行情内 Funding 异常 (`range_regime_funding_extreme`) | `rejected` | `not_daily_event_report` |
| 震荡行情内均值回归家族 (`range_regime_mean_reversion_family`) | `rejected` | `not_daily_event_report` |
| 四袖套共享资金行情路由组合 (`regime_component_shared_capital_combo`) | `rejected` | `not_daily_event_report` |
| 已淘汰策略失败原因聚类 (`rejected_strategy_failure_clusters`) | `meta_only` | `missing_machine_readable_report` |
| 相对强弱持续 (`relative_strength_persistence`) | `rejected` | `not_daily_event_report` |
| 研究风险地图 (`research_risk_map`) | `meta_only` | `not_daily_event_report` |
| 期现基差套利 (`spot_perp_basis`) | `rejected` | `not_daily_event_report` |
| UTC 时段开盘区间突破家族 (`utc_session_breakout_family`) | `rejected` | `not_daily_event_report` |
| 波动率压缩突破 (`vol_compression_breakout`) | `rejected` | `not_daily_event_report` |
| 周频横截面多空动量组合 (`weekly_cross_sectional_momentum`) | `observed_rejected` | `not_daily_event_report` |
| 周频横截面弱势空头（下行） (`weekly_cross_sectional_short_downtrend`) | `historical_rejected` | `not_daily_event_report` |

All safety gates remain closed: `approved_for_paper=[]`, `eligible_for_paper=false`, `safe_to_enable_trading=false`.
