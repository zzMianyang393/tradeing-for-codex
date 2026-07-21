# 日线 RSI 均值回复：适配行情审计

日期：2026-07-13

## 方法

- 来源报告：`reports/daily_rsi_mean_revert_audit.json`
- 新报告：`reports/daily_rsi_mean_revert_regime_conditioned_audit.json`
- 只补入场时已完成 4h 行情标签，不改 RSI 参数。
- 声明适配行情：`震荡`。

## 关键数字

| 区间 | 全部事件 | 全部净收益 | 震荡适配事件 | 震荡适配净收益 |
| --- | ---: | ---: | ---: | ---: |
| Formation | 60 | +446.339126% | 0 | 0.000000% |
| OOS | 142 | +302.720049% | 0 | 0.000000% |

## 判定

`regime_conditioned_rejected`。

这条结果很重要：RSI 裸事件看起来很好，但在当前完成 4h 标签体系下，触发并不发生在 `震荡` 标签中。它不能作为“震荡均值回复方向腿”加入组合矩阵。后续可以单独研究“下行/高波动后的反弹”家族，但不能把它混称为震荡策略。

安全状态：`approved_for_paper=[]`，`safe_to_enable_trading=false`，`ready_for_combo_backtest=false`。
