# 组合特征时间序列诊断（2026-07-13）

## 结论

方向特征抽取继续保持“适配行情事件”口径。本轮将 `daily_rsi_mean_revert` 从旧的 `震荡` 均值回归语义修正为 `趋势下行` 超卖反弹语义后，方向候选仍为 5 个，且 5 个都产生了月度收益序列。

这一步仍然只是只读诊断，不允许启动组合回测。

## 抽取范围

方向候选来自 `reports/feature_pool_preflight_review.json`：

- `feat_donchian_atr_trend_baseline`
- `feat_daily_bb_mean_revert`
- `feat_daily_rsi_mean_revert`
- `feat_daily_trend_pullback`
- `feat_4h_ema_crossover`

## 适配行情过滤

| Feature | 来源报告 | 原始事件 | 保留事件 | Formation | OOS | 过滤方式 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| feat_donchian_atr_trend_baseline | `reports/donchian_atr_trend_baseline_regime_conditioned_audit.json` | 460 | 339 | 166 | 173 | `declared_compatible_regime_only` |
| feat_daily_bb_mean_revert | `reports/daily_bb_mean_revert_regime_conditioned_audit.json` | 23 | 8 | 4 | 4 | `declared_compatible_regime_only` |
| feat_daily_rsi_mean_revert | `reports/daily_rsi_downtrend_rebound_regime_conditioned_audit.json` | 202 | 201 | 59 | 142 | `declared_compatible_regime_only` |
| feat_daily_trend_pullback | `reports/daily_trend_pullback_regime_conditioned_audit.json` | 159 | 21 | 3 | 18 | `declared_compatible_regime_only` |
| feat_4h_ema_crossover | `reports/ema_crossover_4h_regime_conditioned_audit.json` | 856 | 62 | 27 | 35 | `direction_compatible_regime_only` |

方向事件合计：631。

## 月度覆盖

| Feature | 活跃月份 | 零值月份 | 零值占比 |
| --- | ---: | ---: | ---: |
| feat_donchian_atr_trend_baseline | 18 | 7 | 28.00% |
| feat_daily_rsi_mean_revert | 15 | 10 | 40.00% |
| feat_4h_ema_crossover | 14 | 11 | 44.00% |
| feat_daily_trend_pullback | 10 | 15 | 60.00% |
| feat_daily_bb_mean_revert | 5 | 20 | 80.00% |

共同活跃月份仍只有 3 个：`2024-08`、`2025-02`、`2025-06`。

## 解释

RSI 修正是本轮的实质进展：它不再是 0 事件的震荡腿，而是一个 201 事件的下跌趋势反弹弱信号。组合矩阵因此从 430 个方向事件提升到 631 个方向事件。

但组合层仍不能回测，因为全体方向腿共同活跃月份仍不足 12 个月。下一步应改成“分组组合”或“按 regime 分桶组合”，而不是要求所有方向腿同时有事件。

## 继续禁止事项

- 不做组合回测。
- 不做权重优化。
- 不接入 `runner.py`。
- 不生成 paper trading 候选。

## 证据文件

- `daily_rsi_mean_revert_audit.py`
- `directional_regime_conditioned_audit.py`
- `directional_regime_event_inventory.py`
- `combo_feature_timeseries.py`
- `reports/daily_rsi_downtrend_rebound_regime_conditioned_audit.json`
- `reports/combo_feature_timeseries.json`
- `tests/test_directional_regime_conditioned_audit.py`
- `tests/test_directional_regime_event_inventory.py`
- `tests/test_combo_feature_timeseries.py`
