# Canonical Strategy Performance Inventory

Scope: registered directional strategies plus current audited rules. Historical experimental snapshots are excluded.

`事件累计` is the sum of individual net event returns, not an account-level return. `组合收益` is a shared-capital return. Sharpe is only annualized when a daily equity curve exists; otherwise the table labels a nonannualized event-return proxy or `n/a`.

| Strategy | Status | Formation result | OOS result | Aggregate result | Max DD | Sharpe | Basis |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 旧动态路由高收益报告 (`legacy_dynamic_router`) | `invalid` | - | - | - | n/a | n/a | no PnL |
| 相对强弱持续 (`relative_strength_persistence`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| BTC 趋势内山寨回调 (`btc_trend_pullback`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 波动率压缩突破 (`vol_compression_breakout`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 配对统计套利 (`pairs_walk_forward`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 期现基差套利 (`spot_perp_basis`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 多币种资金费率拥挤反转 (`multi_coin_funding_crowding`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| Funding 与 OI 联合信号（原始报告） (`funding_oi_joint_original`) | `invalid` | - | - | - | n/a | n/a | no PnL |
| BTC 对非 BTC 短时领先滞后 (`btc_alt_lead_lag`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 正资金费率市场中性持有 (`positive_funding_carry`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 中周期 Funding Term Carry (`funding_term_carry`) | `rejected` | -0.397% | -1.715% | - | n/a | n/a | event_audit_not_portfolio_equity |
| 跨时间稳定性元审计 (`cross_time_stability`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| 执行成本地板元审计 (`execution_cost_floor`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| 低换手研究门槛元审计 (`low_turnover_research_gate`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| 不交易过滤器候选元审计 (`no_trade_filter_research`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| OKX 免费数据覆盖与流动性地图 (`okx_free_data_liquidity_map`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| 已淘汰策略失败原因聚类 (`rejected_strategy_failure_clusters`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| 冻结家族长期重启条件 (`frozen_family_reactivation_criteria`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| 低换手公开研究方向扫描 (`low_turnover_public_research_scan`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| OI 去杠杆过滤器元审计 (`oi_deleveraging_filter`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| 研究风险地图 (`research_risk_map`) | `meta_only` | - | - | - | n/a | n/a | no PnL |
| Funding 与 OI 联合信号（时间修复版） (`funding_oi_time_corrected`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 震荡行情内 Funding 异常 (`range_regime_funding_extreme`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 日线 OI 独立变化率 (`daily_oi_independent_change`) | `rejected` | - | - | - | n/a | n/a | no PnL |
| 唐奇安通道 + ATR 趋势基准 (`donchian_atr_trend_baseline`) | `rejected` | +713.177% | -84.470% | - | n/a | n/a | event_audit_declared_compatible_regime |
| 日线低换手 90 日动量 (`daily_low_turnover_momentum`) | `rejected` | +73.239% | -70.000% | - | n/a | n/a | event_audit_summary |
| 日线均线多头排列趋势 (`daily_ma_alignment`) | `rejected` | +26.340% | +0.000% | - | n/a | n/a | event_audit_summary |
| 日线布林带均值回复 (`daily_bb_mean_revert`) | `rejected` | -7.746% | +27.688% | - | n/a | n/a | event_audit_declared_compatible_regime |
| 日线 RSI 均值回复 (`daily_rsi_mean_revert`) | `rejected` | +0.000% | +0.000% | - | n/a | n/a | event_audit_declared_compatible_regime |
| 日线趋势内回调 (`daily_trend_pullback`) | `rejected` | -22.300% | -6.771% | - | n/a | n/a | event_audit_declared_compatible_regime |
| 4 小时 EMA20/50 交叉 (`4h_ema_crossover`) | `rejected` | -64.693% | +74.959% | - | n/a | n/a | event_audit_direction_compatible_regime |
| 震荡行情内均值回归家族 (`range_regime_mean_reversion_family`) | `rejected` | -28.424% | -140.376% | - | n/a | n/a | event_audit_summary |
| UTC 时段开盘区间突破家族 (`utc_session_breakout_family`) | `rejected` | -708.372% | -238.681% | - | n/a | n/a | event_audit_summary |
| OKX 交割合约跨期价差 (`okx_futures_calendar_spread`) | `rejected` | n/a | n/a | - | n/a | n/a | additive_event_returns_not_portfolio_equity |
| 日线 Williams %R 震荡反转 (`daily_williams_r_range_reversion`) | `rejected` | -139.951% | -51.604% | - | n/a | -0.064 | additive_event_returns_not_portfolio_equity |
| 日线 Parabolic SAR 趋势 (`daily_parabolic_sar_trend`) | `rejected` | -91.565% | +58.306% | - | n/a | 0.028 | additive_event_returns_not_portfolio_equity |
| 日线 ATR 放大突破 (`daily_atr_expansion_breakout`) | `rejected` | +242.764% | -836.060% | - | n/a | -0.671 | additive_event_returns_not_portfolio_equity |
| 日线成交量确认突破 (`daily_volume_confirmed_breakout`) | `rejected` | -84.638% | -95.536% | - | n/a | -0.217 | additive_event_returns_not_portfolio_equity |
| 四袖套共享资金行情路由组合 (`regime_component_shared_capital_combo`) | `rejected` | - | - | -64.393% | 66.900% | -0.924 | shared_capital_portfolio |
| 网格、马丁与锁仓加仓家族 (`grid_martingale_locking_family`) | `risk_blocked` | - | - | - | n/a | n/a | no PnL |
| 机器学习与动态路由家族 (`ml_dynamic_router_family`) | `frozen` | - | - | - | n/a | n/a | no PnL |
| 外部事件、新闻舆情与宏观方向 (`external_event_news_macro_family`) | `frozen` | - | - | - | n/a | n/a | no PnL |
| 日线 KAMA 趋势 (`daily_kama_trend`) | `historical_rejected` | +191.802% | -169.193% | - | n/a | -0.162 | additive_event_returns_not_portfolio_equity |
| 日线回归通道趋势 (`daily_regression_channel_trend`) | `historical_rejected` | +338.989% | -518.141% | - | n/a | -0.330 | additive_event_returns_not_portfolio_equity |
| 日线 RSI 分位数震荡回归 (`daily_rsi_percentile_range_reversion`) | `insufficient_evidence` | +4.155% | +8.365% | - | n/a | 0.190 | additive_event_returns_not_portfolio_equity |
| 日线 BIAS 震荡回归 (`daily_bias_range_reversion`) | `insufficient_evidence` | -16.533% | +0.000% | - | n/a | n/a | additive_event_returns_not_portfolio_equity |
| 日线 Z-score 震荡回归 (`daily_zscore_range_reversion`) | `insufficient_evidence` | +15.641% | +17.165% | - | n/a | 0.563 | additive_event_returns_not_portfolio_equity |
| 日线 KDJ 震荡回归 (`daily_kdj_range_reversion`) | `insufficient_evidence` | +0.000% | +0.000% | - | n/a | n/a | additive_event_returns_not_portfolio_equity |
| 日线 Spring/Upthrust 反转 (`daily_spring_upthrust_range_reversion`) | `insufficient_evidence` | -4.381% | -2.938% | - | n/a | -0.026 | additive_event_returns_not_portfolio_equity |
| 日线 BB 挤压高波动突破 (`daily_bb_squeeze_high_vol_breakout`) | `insufficient_evidence` | +9.734% | -15.939% | - | n/a | -0.143 | additive_event_returns_not_portfolio_equity |
| 周频横截面弱势空头（下行） (`weekly_cross_sectional_short_downtrend`) | `historical_rejected` | -92.019% | +186.886% | - | n/a | 0.195 | additive_event_returns_not_portfolio_equity |
| 周频横截面多空动量组合 (`weekly_cross_sectional_momentum`) | `observed_rejected` | - | - | +9.429% | 17.397% | n/a | shared_capital_portfolio |
| 冻结趋势弱因子组合诊断 (`frozen_trend_weak_factor_sleeve`) | `historical_combo_diagnostic_rejected` | +0.344% | -6.141% | - | 14.918% | n/a | shared_capital_portfolio |

All rows remain research-only: `approved_for_paper=[]`, `eligible_for_paper=false`, `safe_to_enable_trading=false`.
