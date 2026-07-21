# Routed Signal Replay Contract v1

## 1. 职责边界

本模块是连接四个已验收系统的**纯基础设施层**：

```
MarketStateSnapshotStore ──┐
                           ├── RoutedSignalProvider ──→ Backtester.run_slice(signal_provider=...)
StrategyRegistry ──────────┤
StrategyRouter ────────────┘
ProviderRegistry ──────────┘
```

### 1.1 MarketStateSnapshotStore

**职责：** 按 `(symbol, available_at)` 精确存储和检索 MarketState 快照。

**规则：**
- 拒绝重复键
- 拒绝 naive datetime
- 只返回精确匹配（不向前填充，不插值）
- 缺失快照 → 调用者必须放弃交易

**不负责：**
- 不生成 MarketState（由市场状态计算器负责）
- 不决定何时创建快照（由上层调度负责）

### 1.2 ProviderRegistry

**职责：** 将 `signal_provider_id` 映射到显式注入的 Python callable。

**规则：**
- 禁止动态 import 或字符串执行代码
- 重复 provider_id → 失败
- 缺失 provider → 返回拒绝记录，不调用默认策略

**不负责：**
- 不实现信号逻辑
- 不决定哪些策略可用

### 1.3 RoutedSignalProvider

**职责：** 桥接路由器和 Backtester 的 ExternalSignalProvider 接口。

**调用签名：** `(symbol: str, bars: list[FeatureBar], idx: int) -> Signal | None`

**规则：**
1. 从当前 bar 的时间戳查找精确 MarketState 快照
2. 调用 `route()` 获取 RouteDecision
3. 只有 ROUTE 决策才调用 provider
4. 多个匹配策略 → 只调用优先级最高的第一个
5. Provider 只收到 `bars[:idx+1]`（因果前缀）
6. 不读取账户 PnL、回测阶段或未来数据
7. 记录完整审计日志

**不负责：**
- 不实现策略信号
- 不管理仓位或风险
- 不执行订单

### 1.4 ReplayAudit

**职责：** 记录回放过程的聚合统计和逐条决策日志。

**字段：**
- `total_decisions` — 总决策数
- `route_count` — ROUTE 决策数
- `abstain_count` — ABSTAIN 决策数
- `halt_conflict_count` — HALT_CONFLICT 数
- `halt_unknown_count` — HALT_UNKNOWN 数
- `halt_no_match_count` — HALT_NO_MATCH 数
- `provider_call_count` — provider 调用次数
- `emitted_signal_count` — 产生信号次数
- `missing_snapshot_count` — 快照缺失次数
- `missing_provider_count` — provider 缺失次数
- `future_access_violations` — 未来访问违规次数
- `registry_fingerprint` — 注册中心指纹
- `market_state_schema_version` — schema 版本
- `market_state_config_fingerprint` — config 指纹
- `formal_status` — 固定为 `"infrastructure_only"`

## 2. 因果性保证

### 2.1 时间因果

```
bar_ts = bars[idx].ts
bar_dt = datetime(bar_ts)
snapshot = store.get(symbol, bar_dt)

# 快照时间必须 ≤ 当前 bar 时间
assert snapshot.available_at <= bar_dt
```

- 禁止读取未来快照
- 禁止用最近可用快照向前填充
- 缺失精确快照 → 默认不交易

### 2.2 数据因果

```
causal_bars = bars[:idx + 1]  # 只包含已完成的 K 线
signal = provider(symbol, causal_bars, len(causal_bars) - 1)
```

- Provider 不得看到 `bars[idx+1:]`（未来 K 线）
- Provider 不得访问完整 bars 列表
- Provider 不得读取账户、PnL 或回测阶段

### 2.3 决策因果

```
decision = route(state=snapshot, registry=reg, symbol=sym, available_at=bar_dt)

if decision.decision != ROUTE:
    return None  # 不调用任何 provider
```

- HALT_CONFLICT / HALT_UNKNOWN / HALT_NO_MATCH → 不调用 provider
- 只有 ROUTE → 调用第一个选中的 provider

## 3. 模块不接入 runner.py / executor.py

本模块：
- 不导入 runner.py
- 不导入 executor.py
- 不产生订单
- 不执行交易
- 不管理仓位

唯一的"交易"路径是通过 Backtester.run_slice() 的 signal_provider 参数注入，这只是一个信号生成器，不涉及订单执行。

## 4. 测试清单

| # | 测试 | 验证 |
|---|------|------|
| 1 | 当前时间不能读取未来快照 | future_access_violations += 1 |
| 2 | 缺少精确快照不交易 | missing_snapshot_count += 1 |
| 3 | HALT_CONFLICT 不调用 provider | provider_call_count == 0 |
| 4 | HALT_UNKNOWN 不调用 provider | provider_call_count == 0 |
| 5 | HALT_NO_MATCH 不调用 provider | provider_call_count == 0 |
| 6 | ROUTE 只调用第一优先级 provider | high_called=1, low_called=0 |
| 7 | 未选中的 provider 调用次数为 0 | low_called=[] |
| 8 | provider 只能看到因果 bars 前缀 | len(bars) == idx + 1 |
| 9 | 缺少 provider 时关闭交易 | missing_provider_count += 1 |
| 10 | 重复 provider_id 失败 | ValueError raised |
| 11 | 指纹漂移时关闭交易 | halt_unknown_count += 1 |
| 12 | 同输入重复回放完全一致 | sig1 == sig2 |
| 13 | 日志不包含账户收益 | "equity" not in audit |
| 14 | 合成 provider 产生真实成交 | trades > 0 |
| 15 | 成交时间属于当前切片 | entry_ts ∈ [start, end] |
| 16 | 不调用 runner.py / executor.py | import check |

## 5. 接口示例

```python
from routed_signal_replay_v1 import (
    MarketStateSnapshotStore, ProviderRegistry,
    RoutedSignalProvider, ReplayAudit,
)

# 1. 创建快照存储
store = MarketStateSnapshotStore()
store.put("BTC-USDT-SWAP", available_at_dt, market_state)

# 2. 注册 provider
prov_reg = ProviderRegistry()
prov_reg.register("my_strategy_sp", my_signal_function)

# 3. 创建路由感知 provider
audit = ReplayAudit()
sp = RoutedSignalProvider(registry, store, prov_reg, audit=audit)

# 4. 注入到 Backtester
result = backtester.run_slice(trading, warmup, start_ts, end_ts, signal_provider=sp)

# 5. 检查审计
print(audit.to_dict())
```
