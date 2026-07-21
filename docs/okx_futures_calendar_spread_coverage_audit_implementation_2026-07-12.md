# OKX 交割合约跨期价差覆盖审计器实现记录

日期：2026-07-12

## 结论

已新增覆盖审计器，用于在真实 OKX FUTURES 与 SWAP 数据下载后，检查交割合约换月选择后的可对齐样本是否满足研究准入。

当前状态仍为 `candidate`。覆盖通过不等于策略通过，只表示可以进入下一步价差研究。

## 实现范围

- 新增 `okx_futures_calendar_spread_coverage_audit.py`
- 读取按合约拆分的 FUTURES 1m CSV
- 读取同 family 的 SWAP 1m CSV
- 使用 `okx_futures_calendar_spread_pipeline.py` 中的 72h 强制换月规则
- 只统计被选中交割合约与 SWAP 同时存在的时间戳
- 输出 active days、aligned rows、缺失 futures 行数、不可选择合约行数、gap 信息

## 通过条件

默认 `min_active_days=365`。

覆盖审计通过只代表：

- 至少 365 个 UTC 日期有可对齐数据
- 当前换月规则下存在可用交割合约
- 被选择合约与 SWAP 在时间戳上可对齐

## 下一步

真实数据下载后运行覆盖审计。如果覆盖失败，禁止继续编写策略；如果覆盖通过，才进入价差序列生成与预注册审计。
