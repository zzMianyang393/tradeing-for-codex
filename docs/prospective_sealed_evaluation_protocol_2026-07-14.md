# 前瞻影子信号到期密封评估协议（2026-07-14）

## 适用条件

本协议仅在以下条件全部满足时方可启用：

1. 一条影子信号已完整走满 90 天观察期（maturity_ts 已过）
2. 对应的市场数据在观察期内完整可用
3. `prospective_maturity_audit.json` 中该信号状态为 `mature_awaiting_sealed_evaluation`
4. `prospective_observation_integrity_audit.json` 中 `integrity_status=valid`

## 评估前冻结要求

在启动任何一条信号的密封评估之前，必须冻结：

| 冻结项 | 说明 |
|---|---|
| 评价指标 | 收益、胜率、MFE、MAE、持有期偏差的计算公式不得修改 |
| 成本口径 | 单腿 0.16% 往返，四腿 0.32% 往返，不得调整 |
| 行情标签版本 | 使用 `REGIME_VOCABULARY_VERSION` 冻结版本 |
| 样本聚合规则 | 按因子、按行情、按方向的聚合方式不得修改 |
| 基准比较 | 不得引入事后选择的基准 |

## 评估规则

### 单条信号评估

- 一条信号的 90 天净收益为正或为负，**不构成**保留或淘汰的充分条件
- 单条信号的结果仅作为该因子在该行情下的观察记录
- 不得因单条信号亏损就修改因子参数

### 因子级评估

- 必须在同一因子的所有到期信号聚合后才能评估
- 聚合样本必须 ≥ 10 条信号才有统计意义
- 不得按短期结果（单日、单周、单月）调整因子权重

### 仲裁规则

- 趋势上行中的 `donchian_atr_trend_baseline` 与 `persistent_uptrend_ema20_reclaim_v1` 的仲裁规则由 Codex 后续冻结
- 本协议不得自行设计仲裁逻辑
- 在仲裁规则冻结前，两者均保留为独立观察

## 禁止事项

- 不得因单因子短期结果修改参数
- 不得按 OOS 表现反向调权
- 不得启用 paper trading
- 不得接入 runner.py
- 不得修改因子定义或行情适配
- 不得使用系统当前时间作为评估基准

## 到期后启用流程

```
1. 运行 prospective_maturity_audit.py
2. 确认目标信号 status = mature_awaiting_sealed_evaluation
3. 运行 prospective_observation_integrity_audit.py
4. 确认 integrity_status = valid
5. 冻结评价指标与成本口径
6. 采用 `docs/prospective_sealed_factor_evaluation_card_2026-07-14.md` 的冻结口径
7. 评估结果记录到专用报告，不得回写登记册
```

## 当前状态

- 影子信号总数：28
- 已到期：0
- 未到期：28
- 最早到期：2026-10-09 00:00:00
- 最晚到期：2026-10-12 04:00:00
