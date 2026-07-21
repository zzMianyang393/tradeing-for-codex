# OKX 交割合约历史数据下载器实现记录

日期：2026-07-12

## 结论

已新增 OKX 官方免费历史归档的 FUTURES 下载层，用于 `okx_futures_calendar_spread` 的后续覆盖审计与价差序列构建。

当前状态仍为 `candidate`。本实现只提供数据基础设施，不产生交易信号，不允许进入 paper/live。

## 实现范围

- 新增 `okx_historical_futures_data.py`
- 使用 OKX 官方 `market-data-history` 接口
- 固定 `module=2`
- 固定 `instType=FUTURES`
- 使用 `instFamilyList` 查询，例如 `BTC-USDT`
- 下载 monthly 归档 ZIP
- 仅保留 `confirm=1` 的完整 1m K 线
- 按交割合约单独输出 CSV，避免把不同到期合约直接拼接成伪价格
- 输出每个合约的 `.meta.json`
- 输出 family 级 manifest

## 输出格式

每个交割合约输出：

```text
data/calendar_spread/{instrument}_future_1m.csv
```

字段：

- `timestamp_ms`
- `timestamp_utc`
- `instrument_name`
- `open`
- `high`
- `low`
- `close`
- `volume_quote`

## 研究边界

本下载器不做以下事情：

- 不选择当前/次季合约
- 不做换月
- 不拼接合约价格
- 不计算价差信号
- 不做策略回测

这些步骤必须继续由 `okx_futures_calendar_spread_pipeline.py` 的 spread-first 管线完成。

## 验证

新增测试覆盖：

- manifest 请求必须使用 `instType=FUTURES`
- manifest 请求必须使用 `instFamilyList`
- 下载解析必须过滤未确认 K 线
- 下载解析必须支持指定合约过滤
- 输出必须按交割合约拆分
- metadata 必须标记 `okx_execution_compatible`
