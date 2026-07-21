# OKX 交割合约跨期价差真实覆盖审计

日期：2026-07-12

## 数据窗口

- family：`BTC-USDT`
- FUTURES：OKX 官方 `market-data-history`，`module=2`，`instType=FUTURES`
- SWAP：OKX 官方 `market-data-history`，`module=2`，`instType=SWAP`
- 下载窗口：2025-06-01 至 2026-06-30
- 月度归档数：13

## 覆盖审计结果

报告：`reports/okx_futures_calendar_spread_coverage_audit_202506_202606.json`

- `passed`: true
- `active_days`: 388
- `aligned_rows`: 557760
- `missing_selected_futures_rows`: 0
- `gap_count`: 0
- `largest_gap_minutes`: 0
- `decision`: coverage_ready

## 解释

覆盖通过只表示 BTC-USDT 交割合约与 BTC-USDT-SWAP 在 72h 强制换月规则下具备足够可对齐样本。

这不是策略批准，不允许进入 paper/live。

## 下一步

生成 spread-first 的 1m 价差序列，然后基于预注册规则做价差研究。后续研究必须继续硬编码四腿往返成本不低于 0.32%。
