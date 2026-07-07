# 量化交易系统开发路线

> 最后更新: 2026-07-07
> 策略: 先完成所有CLI/数据/核心逻辑，HTML页面放最后

---

## 当前状态总结

### ✅ 已完成
| 模块 | 文件 | 状态 |
|------|------|------|
| 数据加载 | `market.py` | Bar/FeatureBar/重采样/特征计算全部OK |
| 数据下载 | `okx_downloader.py` | OKX历史K线下载，断点续传+重试 |
| 策略信号 | `strategy.py` | 4个信号生成器（核心/攻击/延续/微观动量） |
| 回测引擎 | `backtester.py` | 事件驱动，多窗口，动态选币，冷却系统 |
| 验证 | `validation.py` + `rolling_window_audit.py` | 多窗口审计 + 滚动审计 |
| 配置 | `config.py` | 100+参数，per-window覆盖 |
| 参数搜索 | ~50个search脚本 | 各维度参数优化 |
| K线数据 | `data/` | 29个币种，73个CSV文件，129MB |
| 风控层 | `risk_manager.py` | 下单前置检查、暂停、风险事件、盘口流动性限制 |
| 状态持久化 | `state_db.py` | SQLite订单/持仓/账户/交易/风控/健康报告 |
| 执行层 | `exchange.py` + `executor.py` + `runner.py` | dry-run、OKX模拟盘检查、订单同步、平仓、监控循环 |
| 扩展数据源 | `funding_rate.py` + `open_interest.py` + `trade_flow.py` + `order_book.py` | 下载、缓存、特征接入、独立模块审计 |
| 监控与报告 | `health_report.py` + `report_cli.py` | 健康检查、状态报告、风险/交易摘要 |
| Web仪表盘 | `dashboard.py` | 本地SQLite静态HTML仪表盘，含权益曲线、视图切换、过滤 |

### ❌ 未完成（按优先级排列）
1. 模拟盘长期连续运行验证（2-4周）和每日复盘闭环。
2. 执行层异常恢复继续增强：网络异常、部分成交、订单失败重试的长期场景压测。
3. 扩展数据源深度仍不足：OI/trade-flow/order-book缓存多数仍偏近端或点状。
4. Optional data-source策略模块滚动审计未达标，不能默认启用。
5. 监控通知还缺主动外部告警（Telegram/邮件等）。
6. Web仪表盘目前是静态HTML，缺本地服务和自动刷新接口。

---

## 开发阶段

### 阶段 1：风控层 — RiskManager
**目标：所有订单在执行前必须过风控检查**

#### 1.1 风控核心 `risk_manager.py`（新建）
```
class RiskManager:
    def check_order(order, portfolio) -> RiskDecision
        - 单币种最大仓位检查
        - 总仓位限制检查
        - 单日最大亏损检查
        - 单周最大亏损检查
        - 连亏暂停检查
        - 波动率异常暂停检查
        - 滑点过大检查
        - 强平距离保护
        - 相关性限仓（可选）

    def on_trade_close(trade) -> None
        - 更新连亏计数
        - 更新日/周PnL统计
        - 触发暂停逻辑

    def get_status() -> RiskStatus
        - 当前风险暴露
        - 是否暂停中
        - 暂停原因
```

#### 1.2 风控配置 `config.py` 扩展
新增字段（不改现有字段）：
```python
# RiskManager 配置
rm_max_single_position_pct: float = 0.40      # 单币种最大仓位占比
rm_max_total_position_pct: float = 0.80       # 总仓位上限
rm_max_daily_loss_pct: float = 15.0           # 单日最大亏损%
rm_max_weekly_loss_pct: float = 30.0          # 单周最大亏损%
rm_consecutive_loss_pause: int = 4            # 连亏N次暂停
rm_consecutive_loss_pause_bars: int = 288     # 暂停N根K线
rm_volatility_halt_threshold: float = 0.06    # ATR%超此值暂停
rm_slippage_halt_threshold: float = 0.003     # 实际滑点超此值暂停
rm_min_liquidation_distance_pct: float = 0.05 # 距强平至少5%
rm_pause_on_inconsistency: bool = True        # 持仓不一致时暂停
```

#### 1.3 接入回测引擎
- `backtester.py` 的 `Backtester.run()` 在开仓前调用 `RiskManager.check_order()`
- 风控拒绝的订单不执行，记录拒绝原因
- 每次平仓后调用 `RiskManager.on_trade_close()`
- 回测报告中新增 `risk_events` 字段，记录所有风控事件

#### 1.4 验收标准
- [ ] `risk_manager.py` 单元测试覆盖所有检查规则
- [ ] 回测中风控拒绝的订单有日志
- [ ] 风控暂停期间不开新仓
- [ ] `backtester.py` 回测结果包含风控统计

---

### 阶段 2：状态持久化 — SQLite
**目标：所有交易状态持久化，可追溯、可对账**

#### 2.1 数据库 schema `state_db.py`（新建）
```sql
-- 订单表
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,  -- 'long' / 'short'
    type TEXT NOT NULL,       -- 'market' / 'limit'
    qty REAL NOT NULL,
    price REAL,
    status TEXT NOT NULL,     -- 'pending'/'filled'/'partial'/'cancelled'/'failed'
    created_at TEXT NOT NULL,
    filled_at TEXT,
    fill_price REAL,
    fill_qty REAL,
    fee REAL,
    signal_reason TEXT,
    risk_decision TEXT,
    meta JSON
);

-- 持仓表
CREATE TABLE positions (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL,
    qty REAL NOT NULL,
    notional REAL NOT NULL,
    margin REAL NOT NULL,
    leverage REAL NOT NULL,
    unrealized_pnl REAL,
    stop_loss REAL,
    take_profit REAL,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL      -- 'open' / 'closed'
);

-- 账户快照表
CREATE TABLE account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    equity REAL NOT NULL,
    available_margin REAL NOT NULL,
    used_margin REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    daily_pnl REAL,
    weekly_pnl REAL,
    open_positions INTEGER,
    risk_status TEXT
);

-- 交易记录表
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    pnl REAL,
    pnl_pct REAL,
    fee REAL,
    signal_reason TEXT,
    exit_reason TEXT,
    regime TEXT,
    risk_events JSON
);

-- 风控事件表
CREATE TABLE risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- 'reject'/'pause'/'resume'/'limit_hit'
    detail JSON
);
```

#### 2.2 数据访问层 `state_db.py`
```python
class StateDB:
    def __init__(self, db_path: Path)
    def save_order(order) -> None
    def update_order_status(order_id, status, ...) -> None
    def save_position(position) -> None
    def close_position(position_id, exit_price, pnl) -> None
    def snapshot_account(equity, ...) -> None
    def save_trade(trade) -> None
    def save_risk_event(event_type, detail) -> None
    def get_open_positions() -> list
    def get_recent_trades(n) -> list
    def get_account_history() -> list
    def reconcile_with_exchange(exchange_positions) -> ReconcileResult
```

#### 2.3 对账机制
```python
class ReconcileResult:
    matches: list       # 本地和交易所一致的持仓
    local_only: list    # 本地有但交易所没有（可能已平仓）
    exchange_only: list # 交易所有但本地没有（异常）

def reconcile(local_positions, exchange_positions) -> ReconcileResult:
    # 对比本地状态和交易所真实持仓
    # 不一致时触发暂停
```

#### 2.4 验收标准
- [ ] SQLite建表/读写正常
- [ ] 每笔订单、持仓、交易都有记录
- [ ] 账户快照按时间序列存储
- [ ] 对账功能可检测不一致
- [ ] 不一致时RiskManager可触发暂停

---

### 阶段 3：模拟盘执行引擎
**目标：策略信号 → 风控检查 → 下单 → 状态同步 → 自动平仓**

#### 3.1 交易所接口 `exchange.py`（新建）
```python
class OKXExchange:
    def __init__(self, api_key, secret, passphrase, sandbox=True)
    def get_account_balance() -> AccountInfo
    def get_positions() -> list[PositionInfo]
    def get_ticker(symbol) -> Ticker
    def place_order(symbol, side, size, order_type, price=None) -> OrderResult
    def cancel_order(order_id, symbol) -> bool
    def get_order_status(order_id, symbol) -> OrderStatus
    def set_leverage(symbol, leverage) -> bool
    def set_position_mode(mode) -> bool  # 'cross' / 'isolated'
```

#### 3.2 执行引擎 `executor.py`（新建）
```python
class Executor:
    def __init__(self, exchange, risk_manager, state_db)
    def execute_signal(signal) -> ExecutionResult
        # 1. RiskManager.check_order()
        # 2. exchange.place_order()
        # 3. state_db.save_order()
        # 4. 等待成交 / 轮询状态
        # 5. state_db.update_order_status()
        # 6. 返回结果

    def manage_positions(current_bars) -> list[Action]
        # 1. 检查止损/止盈/时间退出
        # 2. 检查trailing stop
        # 3. 执行平仓
        # 4. 更新状态

    def sync_state() -> SyncResult
        # 1. exchange.get_positions()
        # 2. state_db.reconcile_with_exchange()
        # 3. 不一致时暂停
```

#### 3.3 运行循环 `runner.py`（新建）
```python
class TradingRunner:
    def __init__(self, config, exchange, executor, state_db)
    def run_once() -> RunReport
        # 1. 获取最新K线
        # 2. 计算特征
        # 3. 生成信号
        # 4. 管理现有持仓
        # 5. 执行新信号
        # 6. 对账
        # 7. 快照账户
        # 8. 返回报告

    def run_loop(interval_seconds=900) -> None
        # 按K线周期循环运行
        # 每个周期执行一次 run_once()
```

#### 3.4 CLI命令 `cli_runner.py`
```bash
python runner.py --status          # 查看当前状态
python runner.py --dry-run         # 模拟运行不实际下单
python runner.py --once            # 只运行一次
python runner.py --loop            # 持续运行
python runner.py --reconcile       # 手动对账
python runner.py --report          # 生成交易报告
```

#### 3.5 验收标准
- [ ] OKX模拟盘连接正常
- [ ] 下单→成交→状态同步全链路OK
- [ ] 止损/止盈/时间退出正常触发
- [ ] 对账检测到不一致时自动暂停
- [ ] dry-run模式不下真单
- [ ] 每笔交易可追溯（信号→风控→订单→成交→PnL）

---

### 阶段 4：扩展数据源
**目标：不只靠K线指标，增加资金费率、OI、主动买卖量**

#### 4.1 资金费率 `data/funding_rate.py`
```python
def fetch_funding_rate(symbol, days) -> list[FundingRate]
def add_funding_features(bars, funding_rates) -> list[FeatureBar]
    # 在FeatureBar中增加:
    # - funding_rate: float
    # - funding_rate_ma: float (7日均线)
    # - funding_rate_zscore: float
```

#### 4.2 持仓量 `data/open_interest.py`
```python
def fetch_open_interest(symbol, days) -> list[OI]
def add_oi_features(bars, oi_data) -> list[FeatureBar]
    # - open_interest: float
    # - oi_change_pct: float
    # - oi_price_divergence: float
```

#### 4.3 主动买卖量 `data/trades_flow.py`
```python
def fetch_trades_flow(symbol, days) -> list[TradesFlow]
def add_flow_features(bars, flow_data) -> list[FeatureBar]
    # - buy_volume: float
    # - sell_volume: float
    # - buy_ratio: float (主动买入占比)
    # - volume_delta: float
```

#### 4.4 新策略信号
在 `strategy.py` 中新增：
```python
def funding_signal_for(symbol, bars, idx, config) -> Signal | None:
    # 资金费率偏离信号

def flow_signal_for(symbol, bars, idx, config) -> Signal | None:
    # 主动买卖量异常信号
```

#### 4.5 验收标准
- [ ] OKX funding rate API数据可下载并缓存
- [ ] 新特征正确附加到FeatureBar
- [ ] 新策略信号独立可回测
- [ ] 向后兼容：没有新数据时旧策略照常运行

---

### 阶段 5：监控与CLI报告
**目标：系统跑起来后能知道它为什么赚钱、为什么亏钱**

#### 5.1 交易日志 `logging_config.py`
```python
# 结构化日志，写入 trades.log
# 每条记录包含: 时间、币种、方向、信号原因、风控判断、下单价格、成交价格、PnL、退出原因
```

#### 5.2 CLI报告工具 `report_cli.py`
```bash
python report_cli.py daily           # 今日交易总结
python report_cli.py weekly          # 本周复盘
python report_cli.py performance     # 策略表现拆分
python report_cli.py risk            # 风控状态
python report_cli.py positions       # 当前持仓
python report_cli.py equity-curve    # 权益曲线（终端ASCII图）
python report_cli.py audit           # 运行rolling audit
```

#### 5.3 告警通知（可选）
```python
# 通过Hermes cron + Telegram推送
# 异常时发送告警: 连亏、大额亏损、对账不一致、API错误
```

#### 5.4 验收标准
- [ ] 每日交易总结可自动生成
- [ ] 策略/币种/regime维度的PnL拆分
- [ ] 风控状态一览
- [ ] 异常可主动通知（Telegram）

---

### 阶段 6：反过拟合验证增强
**目标：任何配置进入默认前都必须过硬闸门**

#### 6.1 Walk-Forward测试 `walk_forward.py`（新建）
```python
def run_walk_forward(data_dir, config, train_days, test_days, step_days):
    # 滚动切分训练/测试集
    # 训练集优化参数 → 测试集验证
    # 输出每个切分的OOS表现
```

#### 6.2 参数敏感性测试 `param_sensitivity.py`（新建）
```python
def run_sensitivity(data_dir, config, param_ranges):
    # 对每个关键参数 ±10%/±20% 扰动
    # 测试收益变化幅度
    # 变化过大 → 疑似过拟合
```

#### 6.3 蒙特卡洛扰动 `monte_carlo.py`（新建）
```python
def run_monte_carlo(trades, n_simulations=1000):
    # 随机打乱交易顺序
    # 统计最差情况下的最大回撤
    # 评估收益的稳定性
```

#### 6.4 验收标准
- [ ] Walk-forward测试可运行并输出报告
- [ ] 参数敏感性测试标记不稳定参数
- [ ] 蒙特卡洛给出置信区间
- [ ] 所有验证结果写入JSON报告

---

### 阶段 7：Web仪表盘（最后做）
**目标：可视化查看交易状态**

> 前面6个阶段全部CLI完成后再做这个
> 使用简单的Flask/FastAPI + 前端HTML

- 权益曲线图
- 当前持仓表
- 最近交易表
- 风控状态面板
- 策略表现对比

---

## 开发顺序总结

```
阶段1: 风控层 ──────────── CLI，无前端，核心逻辑
    ↓
阶段2: 状态持久化 ──────── SQLite，无前端，数据层
    ↓
阶段3: 模拟盘执行 ──────── OKX API，CLI，核心逻辑
    ↓
阶段4: 扩展数据源 ──────── 数据下载+特征，无前端
    ↓
阶段5: 监控与报告 ──────── CLI工具，终端输出
    ↓
阶段6: 反过拟合增强 ────── 纯计算，无前端
    ↓
阶段7: Web仪表盘 ──────── HTML，最后做
```

每个阶段都有明确的验收标准，完成后进入下一阶段。
阶段1-3是核心骨架（约2-4周），阶段4-6是增强（约2-3周），阶段7是锦上添花。
