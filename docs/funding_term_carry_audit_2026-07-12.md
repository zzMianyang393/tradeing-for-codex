# Funding Term Carry 审计

日期：2026-07-12

## 结论

淘汰。该规则不允许接入 `runner.py`，不允许进入 paper trading。

## 与已淘汰短周期 funding 策略的区别

本审计不是 funding 结算窗口抢跑，也不是裸方向交易。规则为：

- 持仓：long spot / short perpetual
- 信号：已结算 funding 的 7 日滚动均值
- 阈值：当前 7 日均值高于同一标的过去 180 天 80% 分位数
- 入场：已知 funding 结算后的下一个 15m 开盘
- 出场：固定持有 14 天
- 收益：未来 funding 收入 + spot/perp 对冲残差 - 四腿往返成本
- 成本：0.32%
- 参数扫描：无

## 数据

- BTC：OKX funding + spot/perp 1m basis 数据
- ETH：OKX funding + spot/perp 1m basis 数据
- basis 覆盖：2024-07 至 2026-06

由于该规则需要 180 天分位数预热，形成期从 2025-01-01 开始：

- formation：2025-01-01 至 2025-07-10
- OOS：2025-07-11 至 2026-06-10

## 结果

形成期：

- 事件数：4
- 净收益合计：-0.396919%
- 净收益均值：-0.099230%
- 净收益中位数：-0.108603%
- 胜率：0.0000%
- funding 收入均值：+0.217673%
- hedge return 均值：+0.003097%

样本外：

- 事件数：16
- 净收益合计：-1.714605%
- 净收益均值：-0.107163%
- 净收益中位数：-0.100042%
- 胜率：37.5000%
- funding 收入均值：+0.216558%
- hedge return 均值：-0.003721%

## 淘汰原因

触发以下淘汰条件：

- formation 事件数 4，小于最低门槛 10
- formation 净均值为负
- formation 胜率 0%，低于 52%
- OOS 净均值为负
- OOS 胜率 37.5%，低于 50%
- OOS 最大单月正收益贡献 56.43%，超过 25%

## 解释

该方向的失败不是因为 funding 收入不存在。BTC/ETH 在信号触发后的 14 天 funding 收入均值约为 0.22%，但四腿往返成本硬地板为 0.32%，成本已经超过主要收益来源。spot/perp 对冲残差非常小，无法稳定补足成本缺口。

因此，Funding Term Carry 在当前免费 OKX 数据和保守执行成本下，不具备独立可交易性。它未来可以作为资金费率状态描述或风险过滤器参考，但不能作为开仓策略。

## 产物

- 脚本：`funding_term_carry_audit.py`
- 测试：`tests/test_funding_term_carry_audit.py`
- 报告：`reports/funding_term_carry_audit.json`
