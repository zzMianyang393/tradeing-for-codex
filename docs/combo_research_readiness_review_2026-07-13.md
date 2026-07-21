# 组合研究就绪度审查（2026-07-13）

## 结论

当前不允许启动组合回测。下一步仅允许做只读的特征时间序列抽取与诊断。

## 当前特征池状态

| 分类 | 数量 |
|---|---:|
| directional_feature_candidates | 2 |
| context_label_candidates | 17 |
| risk_filter_candidates | 4 |
| blocked_features | 11 |

当前方向候选：

- `donchian_atr_trend_baseline`
- `daily_bb_mean_revert`

二者都带有 `concentration_risk`，必须在任何后续组合研究中启用单月贡献惩罚。

## 阻断原因

- 方向特征数 2 < 3，低于组合回测最低门槛。
- 当前所有方向候选都需要集中度惩罚，没有任何一个干净的无集中度方向弱信号。

## 允许的下一步

- 抽取 feature 时间序列。
- 计算方向特征之间的相关性。
- 统计月度贡献与剔除 2024-11 后的表现。
- 验证 context label 和 risk filter 是否只能作为过滤/状态，不产生方向开仓。

## 禁止事项

- 不启动组合回测。
- 不做权重优化。
- 不接入 `runner.py`。
- 不生成 paper trading 候选。
- 不根据 OOS 表现反向调权。

## 证据文件

- `combo_research_readiness_review.py`
- `reports/combo_research_readiness_review.json`
- `tests/test_combo_research_readiness_review.py`
