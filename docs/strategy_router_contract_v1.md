# Strategy Router Contract v1

Router v1强制绑定 MarketState schema `v1.0.0` 与已冻结的完整配置指纹；调用方不能省略或替换该校验。注册中心与描述符使用完整64位 SHA-256。周线与日线出现方向相反时，即使上游遗漏了 `StateConflict`，路由器也会自行检测并返回 `HALT_CONFLICT`。

## 1. 职责边界

本系统由四个独立层组成，各层职责严格分离：

### 1.1 策略注册中心 (`strategy_registry_v1.py`)

**职责：** 描述策略"是什么"和"何时可用"。

- 定义 `StrategyDescriptor`（不可变策略元数据）
- 管理 `StrategyRegistry`（不可变策略集合）
- 验证描述符合法性（枚举值、必填字段、唯一性）
- 产生确定性指纹
- 筛选可路由候选（`is_routable`）

**不负责：**
- 不判断策略是否赚钱
- 不实现交易信号
- 不访问回测结果或账户数据
- 不动态加载策略代码

### 1.2 多周期路由器 (`strategy_router_v1.py`)

**职责：** 将 MarketState 匹配到已注册的策略。

- 纯函数：相同输入 → 相同输出
- 检查方向/风险大门（周线 > 日线 > 4h）
- 检查 regime 匹配（4h tradable_regime）
- 检查跨周期冲突
- 稳定排序候选（priority, strategy_id）
- 产生 RouteDecision

**不负责：**
- 不产生交易信号
- 不判断策略盈亏
- 不访问账户数据
- 不执行订单

### 1.3 信号策略 (future task)

**职责：** 给定已路由的策略和市场数据，产生具体的入场/出场信号。

- 实现 `signal_provider_id` 对应的信号逻辑
- 使用已完成的 K 线数据
- 遵守 frozen 参数

**不负责：**
- 不决定哪些策略可用（由注册中心决定）
- 不决定当前行情是否适合（由路由器决定）
- 不管理仓位或风险

### 1.4 风险袖套 (future task)

**职责：** 管理仓位大小、止损、资金分配。

- 按 `sleeve_type` 分组管理
- 执行 risk_per_trade、max_positions 等约束
- 管理冷却期和暂停

**不负责：**
- 不选择策略
- 不产生信号

## 2. 路由优先级和冲突处理规则

### 2.1 时间帧层级

```
周线 (1w)  ─── 方向/风险大门（最高优先级）
  │
日线 (1d)  ─── 方向确认
  │
4h        ─── Regime 匹配（trend_following / mean_reversion / no_trade）
  │
15m       ─── 入场时机（最低优先级，不能推翻上层方向）
```

### 2.2 路由决策流程

1. **预检**
   - `available_at` 一致性
   - MarketState schema 版本匹配
   - MarketState config 指纹匹配

2. **冲突检查**
   - 严重跨周期方向冲突 → `HALT_CONFLICT`
   - 严重冲突字段：`direction`, `direction_regime`
   - 严重冲突定义：severity = "high" 且 field ∈ `_SEVERE_CONFLICT_FIELDS`

3. **逐策略筛选**
   - `research_status` ∈ {formation_eligible, frozen}
   - `symbol_scope` 包含当前 symbol（或为空 = 全部）
   - `required_timeframes` 全部非 unknown
   - `confidence` ≥ `minimum_confidence`
   - `supported_regimes` 包含当前 4h regime
   - `supported_directions` 包含当前市场方向
   - 非 `allowed_conflict_fields` 中的冲突 → 拒绝

4. **排序和选择**
   - 按 `(priority ASC, strategy_id ASC)` 稳定排序
   - 无匹配 → `HALT_NO_MATCH`

### 2.3 冲突处理

| 冲突类型 | 严重度 | 路由行为 |
|----------|--------|----------|
| 1w vs 1d direction | high | HALT_CONFLICT |
| 1d vs 4h direction_regime | medium | 策略可声明容忍 |
| 4h vs 15m direction | medium | 策略可声明容忍 |
| 1w vs 4h volatility | medium | 策略可声明容忍 |

## 3. 为什么路由匹配 ≠ 策略获利验证

路由匹配只检查**结构性条件**：
- 当前行情方向是否允许该策略方向
- 当前 regime 是否在策略适用范围内
- 必需的时间帧数据是否可用

路由匹配**不检查**：
- 该策略在类似行情中是否盈利
- 该策略的胜率或收益
- 该策略的回测表现
- 当前市场是否"好"或"坏"

一个策略被路由选中，只意味着"当前行情结构符合该策略的适用声明"，不意味着"现在交易该策略会赚钱"。盈亏验证必须通过独立的 Formation/Validation/OOS 流程完成。

## 4. 为什么 Validation/OOS 不能反向改变注册条件

注册中心的 `StrategyDescriptor` 是**先验声明**：
- "我在 trend_following regime 下可用"
- "我需要 1d 和 4h 数据非 unknown"
- "我的最低置信度是 0.5"

这些声明在策略设计时确定，不能因为回测结果好就放宽条件，也不能因为回测结果差就收紧条件。

如果允许回测结果反向修改注册条件：
- 注册信息变成后验的（overfitting to backtest）
- 同一策略在不同回测窗口会变成不同的"策略"
- 失去可重复性

正确的流程是：
1. 策略在 Formation 期间被评估
2. 如果通过 Formation → 升级为 `formation_eligible`
3. 如果通过 Validation → 升级为 `frozen`
4. 如果 OOS 失败 → 降级为 `rejected`
5. 状态变更记录在案，不修改原始描述符

## 5. 当前模块状态

### 5.1 已实现

- `StrategyDescriptor` — 不可变策略描述符
- `StrategyRegistry` — 不可变策略集合，带唯一性验证和指纹
- `route()` — 纯函数路由器，MarketState → RouteDecision
- 完整测试覆盖（14 个测试类，30+ 测试用例）

### 5.2 未实现 / 未接入

- **未接入 `runner.py`** — 路由器不在任何交易循环中被调用
- **未接入 `backtester.py`** — 路由器不在回测中被调用
- **未实现信号策略** — `signal_provider_id` 只是引用标识符，不触发代码加载
- **未实现风险袖套** — `sleeve_type` 只是分类标签
- **不允许模拟盘或实盘** — 没有任何代码路径将路由决策转化为订单

### 5.3 接口约定

```python
# 路由器的唯一入口
decision = route(
    state=market_state,       # MarketState from market_state_schema
    registry=strategy_registry,  # StrategyRegistry
    symbol="BTC-USDT-SWAP",
    available_at=timestamp,
    expected_schema_version="v1.0.0",           # optional
    expected_config_fingerprint="...",          # optional
)

# 路由器的唯一输出
decision.decision           # RouteDecisionType
decision.selected_strategy_ids  # tuple[str, ...]
decision.rejected_candidates    # tuple[RejectedCandidate, ...]
decision.reason_codes           # tuple[str, ...]
```

## 6. 测试清单

| # | 测试 | 文件 |
|---|------|------|
| 1 | uptrend 策略不会在 downtrend 中被启用 | test_strategy_router_v1.py |
| 2 | range 策略不会在 trend regime 中被启用 | test_strategy_router_v1.py |
| 3 | 15m 方向不能推翻日线/4h 大方向 | test_strategy_router_v1.py |
| 4 | 严重方向冲突返回 HALT_CONFLICT | test_strategy_router_v1.py |
| 5 | required timeframe 为 unknown 时拒绝 | test_strategy_router_v1.py |
| 6 | prototype/rejected/disabled 不能被路由 | test_strategy_router_v1.py |
| 7 | 没有匹配策略时不启用默认策略 | test_strategy_router_v1.py |
| 8 | 同输入重复执行结果及指纹一致 | test_strategy_router_v1.py |
| 9 | 候选注册顺序变化不会改变最终结果 | test_strategy_router_v1.py |
| 10 | available_at 不一致时拒绝 | test_strategy_router_v1.py |
| 11 | schema/config 指纹不匹配时拒绝 | test_strategy_router_v1.py |
| 12 | 路由过程不访问账户收益和回测阶段 | test_strategy_router_v1.py |
| 13 | 非法枚举、重复ID、非法优先级在注册时失败 | test_strategy_registry_v1.py |
| 14 | trend/range/downtrend 三种合成策略测试 | test_strategy_router_v1.py |
