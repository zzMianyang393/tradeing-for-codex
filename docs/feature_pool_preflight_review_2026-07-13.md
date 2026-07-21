# 组合特征池前置预检审查报告 (2026-07-13)

本报告对组合特征池中的所有研究特征进行前置安全审查，按复用属性分类归档，并验证组合层安全防线状态。

---

## 一、安全防线状态

| 检查项 | 状态 |
|---|---|
| approved_for_paper | [] (空) |
| safe_to_enable_trading | false |
| 所有 feature eligible_for_paper | false |
| 所有 feature allowed_as_standalone | false |
| 验证违规 | 0 |

---

## 二、特征池分类审查列表

### 1. 方向性弱信号候选 (`directional_feature_candidates`)
数量：2

| 特征 ID | 原始研究 ID | 原始状态 | 集中度惩罚 |
|---|---|---|---|
| feat_donchian_atr_trend_baseline | donchian_atr_trend_baseline | rejected | ✅ concentration_risk |
| feat_daily_bb_mean_revert | daily_bb_mean_revert | rejected | ✅ concentration_risk |

### 2. 状态环境特征候选 (`context_label_candidates`)
数量：17

| 特征 ID | 原始研究 ID | 原始状态 | 标签 |
|---|---|---|---|
| feat_relative_strength_persistence | relative_strength_persistence | rejected | oos_decay |
| feat_btc_trend_pullback | btc_trend_pullback | rejected | negative_formation_edge |
| feat_vol_compression_breakout | vol_compression_breakout | rejected | insufficient_events |
| feat_funding_term_carry | funding_term_carry | rejected | funding_overheat_context, cost_friction_failed_as_strategy |
| feat_daily_ma_alignment | daily_ma_alignment | rejected | insufficient_events, no_oos_entries |
| feat_daily_low_turnover_momentum | daily_low_turnover_momentum | rejected | insufficient_events |
| feat_cross_time_stability | cross_time_stability | meta_only | meta_only |
| feat_execution_cost_floor | execution_cost_floor | meta_only | meta_only |
| feat_low_turnover_research_gate | low_turnover_research_gate | meta_only | meta_only |
| feat_no_trade_filter_research | no_trade_filter_research | meta_only | meta_only |
| feat_okx_free_data_liquidity_map | okx_free_data_liquidity_map | meta_only | meta_only |
| feat_rejected_strategy_failure_clusters | rejected_strategy_failure_clusters | meta_only | meta_only |
| feat_frozen_family_reactivation_criteria | frozen_family_reactivation_criteria | meta_only | meta_only |
| feat_low_turnover_public_research_scan | low_turnover_public_research_scan | meta_only | meta_only |
| feat_oi_deleveraging_filter | oi_deleveraging_filter | meta_only | meta_only |
| feat_research_risk_map | research_risk_map | meta_only | meta_only |
| feat_funding_oi_time_corrected | funding_oi_time_corrected | rejected | timing_corrected_no_edge |

### 3. 风险/不交易过滤器候选 (`risk_filter_candidates`)
数量：4

| 特征 ID | 原始研究 ID | 原始状态 | 标签 |
|---|---|---|---|
| feat_multi_coin_funding_crowding | multi_coin_funding_crowding | rejected | funding_crowding_risk |
| feat_range_regime_funding_extreme | range_regime_funding_extreme | rejected | funding_extreme_risk |
| feat_daily_oi_independent_change | daily_oi_independent_change | rejected | meta_only_oi_leverage |
| feat_range_regime_mean_reversion_family | range_regime_mean_reversion_family | rejected | range_false_breakout_risk |

### 4. 组合禁用特征列表 (`blocked_features`)
数量：11

| 特征 ID | 原始研究 ID | 原始状态 | 禁用原因 |
|---|---|---|---|
| feat_legacy_dynamic_router | legacy_dynamic_router | invalid | Invalid research: data/timing issues. |
| feat_pairs_walk_forward | pairs_walk_forward | rejected | No pair passed strict formation/OOS/FDR gates. |
| feat_spot_perp_basis | spot_perp_basis | rejected | Cost-friction failure: spread edge cannot cover four-leg execution. |
| feat_funding_oi_joint_original | funding_oi_joint_original | invalid | Invalid research: data/timing issues. |
| feat_btc_alt_lead_lag | btc_alt_lead_lag | rejected | High-turnover short-horizon edge is negative after cost. |
| feat_positive_funding_carry | positive_funding_carry | rejected | Cost-friction failure: no formation event clears four-leg carry cost. |
| feat_utc_session_breakout_family | utc_session_breakout_family | rejected | High-turnover 15m breakout family failed after cost. |
| feat_okx_futures_calendar_spread | okx_futures_calendar_spread | rejected | Cost-friction failure: four-leg calendar spread audit failed. |
| feat_grid_martingale_locking_family | grid_martingale_locking_family | risk_blocked | Risk blocked: grid/martingale/locking family. |
| feat_ml_dynamic_router_family | ml_dynamic_router_family | frozen | Frozen: insufficient data or ML overfitting risk. |
| feat_external_event_news_macro_family | external_event_news_macro_family | frozen | Frozen: insufficient data or ML overfitting risk. |

---

## 三、结论与纪律

1. **红线阻断**：处于 `blocked_features` 列表中的特征在编写组合回测时一律禁止加载。
2. **相关性审查**：通过预检的方向特征在配权前必须经过共线性审计，相关性系数 ≥ 0.70 的特征组合不可用于开仓投票。
3. **集中度惩罚**：标注 `concentration_risk` 的特征必须在组合层应用单月贡献度惩罚。
4. **样本外缺失**：标注 `no_oos_entries` 的特征已降级为 context_label，不得作为方向信号。
5. **成本吞噬禁复活**：已明确因四腿成本、短周期高换手成本或 FDR 全失败而淘汰的特征，不得借组合名义进入方向池。
6. **语义仲裁优先**：`funding_term_carry` 可保留为 funding 过热 context，但不得方向开仓；`utc_session_breakout_family` 因 15m 高频成本磨损进入 blocked。
7. **不得改变原始信号**：组合层不得修改任何原始特征的历史信号定义。
