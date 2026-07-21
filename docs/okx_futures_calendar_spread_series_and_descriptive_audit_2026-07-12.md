# OKX 交割合约跨期价差序列与描述性审计

日期：2026-07-12

## 输入

- 数据目录：`data/calendar_spread_btc_202506_202606`
- FUTURES：按交割合约拆分的 1m CSV
- SWAP：`BTC-USDT_swap_1m.csv`
- 换月：到期前 72h 强制切换
- 成本地板：四腿往返不低于 0.32%

## 价差序列

输出：`data/calendar_spread_btc_202506_202606/BTC-USDT_calendar_spread_1m.csv`

- `rows`: 557760
- `first_timestamp_utc`: 2025-06-01 00:00:00
- `last_timestamp_utc`: 2026-06-23 07:59:00
- 构造方式：`spread_first_no_futures_price_stitching`

## 描述性审计

报告：`reports/okx_futures_calendar_spread_descriptive_audit.json`

该审计不产生交易信号，只检查价差幅度相对四腿成本地板是否具备继续研究空间。

结果：

- `rows`: 557760
- `active_days`: 388
- `cost_floor`: 0.0032
- `abs_spread_ge_cost_rows`: 67563
- `abs_spread_ge_cost_ratio`: 0.12113274526678142
- `spread_pct_mean`: 0.0017593042856378532
- `spread_pct_p50`: 0.0015432529415
- `spread_pct_p95`: 0.004778996171699995
- `abs_spread_pct_p50`: 0.001562812722
- `abs_spread_pct_p75`: 0.0023712126497499996
- `abs_spread_pct_p95`: 0.00480083267629999
- `abs_spread_pct_p99`: 0.006461901279460003

## 结论边界

覆盖通过与描述性幅度充足都不等于策略批准。后续必须先形成预注册交易规则，再做形成期与样本外审计。
