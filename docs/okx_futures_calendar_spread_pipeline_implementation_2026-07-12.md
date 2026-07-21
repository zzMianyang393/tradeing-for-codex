# OKX 交割合约跨期价差管线实现说明

日期：2026-07-12

## 当前完成范围

已新增离线可测试的数据管线原语：

- `okx_futures_calendar_spread_pipeline.py`
- `tests/test_okx_futures_calendar_spread_pipeline.py`

该实现只处理数据管线最容易出错的基础约束，不生成任何交易信号，不接入 `runner.py`，不接入 `candidate_strategies.py`。

## 已锁定的规则

### 1. 合约代码解析

支持解析 OKX 交割合约代码：

```text
BTC-USDT-260925
```

并映射为：

```text
family = BTC-USDT
expiry_ts = 2026-09-25 08:00:00 UTC
```

非交割合约代码，例如 `BTC-USDT-SWAP`，会被拒绝。

### 2. 无前视合约选择

合约选择函数只允许选择：

- 同一 `family`；
- `listed_ts <= t` 的合约；
- 当前时间 `t` 早于强制换月时间的合约。

这避免在历史时间点读取未来才上市的合约代码。

### 3. 72 小时强制换月

强制换月时间：

```text
rollover_ts = expiry_ts - 72h
```

例如 `BTC-USDT-240927` 到期时间为 `2024-09-27 08:00:00 UTC`，则从
`2024-09-24 08:00:00 UTC` 起不再允许选择该旧合约。

### 4. Spread-first 输出

管线不拼接交割合约价格，也不生成伪连续价格。

每个时间点先选择当时可用的交割合约，再与同时间戳永续价格计算：

```text
spread_abs = future_close - swap_close
spread_pct = spread_abs / swap_close
```

后续如要计算均值、分位数、通道或信号，只能基于 `spread_abs` 或 `spread_pct`，不能基于拼接后的 futures price。

### 5. 成本底线

已硬编码研究成本底线：

```text
四腿完整往返成本: 0.0032
换月两腿成本: 0.0016
```

低于 `0.0032` 的跨期往返成本会被测试拒绝。

## 仍未完成

本次没有下载真实 OKX FUTURES 历史归档，也没有证明 365 天 FUTURES/SWAP 对齐覆盖。

仍未完成的前置门槛：

- FUTURES 月度归档下载器；
- 交割合约列表/上市时间元数据获取；
- 至少 365 天 1m FUTURES/SWAP 覆盖审计；
- 20+ 个币种覆盖证明；
- 换月点真实数据缺口/重复检查；
- 任何收益审计。

## 当前状态

`okx_futures_calendar_spread` 仍保持 `candidate`，不可交易，不可模拟盘。

下一步只能做数据下载器和覆盖审计，仍不能写价差交易策略。
