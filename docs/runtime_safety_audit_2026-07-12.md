# 运行时安全审计（2026-07-12）

## 决策

当前没有通过验证、可进入模拟盘或实盘的策略。因此正常 `runner.py` CLI 不能通过
`--enable-rule-strategies` 或 `--enable-pairs` 启动旧规则策略或实验配对交易。

## 审计结果

- `BacktestConfig` 默认关闭 `enable_rule_trading`、`enable_pairs_trading`、候选池、ML、
  funding、OI、主动成交和盘口模块。
- `TradingRunner.run_once()` 只有 `enable_rule_trading=True` 才生成单币规则信号，只有
  `enable_pairs_trading=True` 才运行配对开仓循环。
- CLI 过去允许用两个显式开关重开未批准模块；现已硬性拒绝并返回 JSON 错误与退出码 `2`。
- 已有持仓的风控退出、状态查询、对账、健康报告与 OKX 模拟账户维护路径不受影响。

## 边界

底层配对和规则引擎仍保留供隔离单元测试和未来研究使用；只有出现经过形成期、样本外、
成本和组合验证的策略，并由项目决策显式解除该保护后，才能修改 CLI 审批规则。
