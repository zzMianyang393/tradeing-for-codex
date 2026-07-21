# 新会话交接：OKX EA 研究（2026-07-12）

## 当前一句话结论

**EA 的执行、回测、数据审计与安全保护已经存在，但当前没有任何获准进入模拟盘或实盘的策略。**

目标仍是自动 EA，不是停止研究；只是当前研究宇宙已经没有剩余候选策略，不能再用调参和旧报告制造表面收益。

## 当前硬规则

1. 只用免费、公开、可复现数据；不购买历史数据、不订阅付费数据 API。
2. OKX 执行结论只能用 OKX 同市场数据；Binance 等只能作为研究代理。
3. 单一策略只需在其预先声明的适用行情中验证；动态组合才按全年 365 天考核。
4. 信号必须在信息实际可用后，于下一根可成交价格入场。
5. 必须包含真实手续费、滑点与完整交易腿数；现货/永续市场中性为四腿成本。
6. 形成期失败直接淘汰；不得通过改 RSI/EMA/ATR、止盈止损、持仓期、币种集合、杠杆、阈值来重跑。
7. 未批准策略不能进入模拟盘或实盘。
8. 工作区很脏，禁止 `git reset --hard`、`git checkout --` 或清理他人改动。

## 程序与安全状态

- `runner.py` 默认关闭规则交易与配对交易。
- Codex 新增 CLI 硬保护：`--enable-rule-strategies` 与 `--enable-pairs` 会被拒绝，因为当前没有获批策略。
- `research_approval_registry.py` 输出机器可读研究状态：当前 `approved_for_paper=[]`、`safe_to_enable_trading=false`。
- 当前注册表状态：`rejected=15`、`invalid=2`、`risk_blocked=1`、`frozen=2`、`meta_only=8`、`candidate=0`。
- 重点文件：
  - `research_approval_registry.py`
  - `reports/research_approval_registry.json`
  - `docs/research_approval_registry_2026-07-12.md`
  - `docs/runtime_safety_audit_2026-07-12.md`

## 数据状态

`reports/research_data_gate_post_download.json` 显示年度合格数据从 32 提升至 77：

- OKX 15m OHLCV：28 个币种年度合格；BTC/ETH 覆盖更长。
- OKX funding：25 个币种年度合格。
- OKX 日线 OI：24 个币种年度合格，实际可用时间为当日 `16:00 UTC`。
- OKX BTC/ETH 现货+永续 1m：约两年，可做基差研究。
- 高频 OI、逐笔成交、订单簿、清算、标记/指数价格 K 线、期权数据：免费历史深度不足，冻结。

## 已完成基础设施

- `unified_validation.py`：统一候选真实信号、成本、仓位、风控、退出和策略指纹。
- `regime_validation.py`：基于完成 4h K 线的趋势上行/下行、震荡、高波动标签。
- `research_data_gate.py`：数据来源、覆盖、同源性资格审计。
- `candidate_signal_audit.py`：下一根 15m 成交的入场延伸、MFE/MAE 审计。
- `pairs_walk_forward.py`：配对形成期/样本外验证。
- `cross_time_stability_audit.py`：前后窗口数据稳定性元审计。
- `btc_alt_lead_lag_audit.py`、`funding_carry_audit.py`：低内存事件研究样例。

## 已淘汰或作废的研究

### 规则型与价格类

- 相对强弱、相对强弱持续：样本外失败，高延伸追强更差。
- 多周期确认、低换手趋势、日内反转、量价背离、波动率状态、波动率压缩、量能衰竭、冲击反转：失败、成本敏感或样本不足。
- BTC 趋势内山寨回调：形成期整体 `-7.36%`，趋势上行标签也为负。
- BTC→非 BTC 短时领先滞后：180 天 2,368 事件，成本前后均为负。

### 衍生/市场中性

- 期现基差/基差微结构：基差量级远低于四腿成本；方向 A 淘汰。
- 正资金费率现货多/永续空：没有足以覆盖四腿成本的事件。
- 多币种 funding 拥挤反转：方向 E 淘汰，收益负且无法覆盖成本。
- 配对统计套利：严格形成期、样本外、多重检验均无通过配对。
- 原生日线 OI/主动买卖量：跨 BTC/ETH 方向不一致或样本不足。

### Funding + OI（最重要）

- 原始 Funding+OI 报告为 `invalid`：它把当天完整 funding 和日线 OI 用于当天 `00:00` 入场，存在前视偏差。旧正收益严禁引用。
- 时间修复版已完成：OI 在 `16:00 UTC` 可用、最早 `16:15` 入场、成本 `0.14%`、形成期/OOS 分割。
- 修复后形成期（2024-07-10 至 2025-01-08）26 事件，4h 净收益 `-0.74%`、胜率 `41.3%`，跨币种不一致。
- 最终状态：`rejected`，不得调阈值继续搜索。
- 证据：`docs/funding_oi_trend_confirmation_repaired_2026-07-12.md`、`reports/funding_oi_trend_confirmation_repaired.json`。

## 跨时间审计给出的约束

- 相对稳定：日线 OI 指标、OHLCV 的波动率/成交量特征。
- 不稳定：收益均值方向、funding 绝对水平/极端频率、跨币种相关性。
- 含义：不能用固定收益预期、固定 funding 阈值、静态币对关系；若未来研究 funding，必须使用滚动分位数归一化；配对必须滚动校准。

## 最新研究收口

2026-07-12 后续已完成原 F1/F2/F3 全部方向：

- F1 日线 OI 独立变化率：`rejected`。
- F2 震荡行情内 Funding 异常：`rejected`。
- F3 OKX 交割合约跨期价差：真实数据覆盖通过，但预注册均值回归规则形成期和样本外均失败，`rejected`。

关键新证据：

- `docs/daily_oi_independent_change_audit_2026-07-12.md`
- `docs/range_regime_funding_extreme_audit_2026-07-12.md`
- `docs/okx_futures_calendar_spread_mean_reversion_audit_2026-07-12.md`
- `docs/research_universe_postmortem_and_next_direction_2026-07-12.md`

当前没有任何研究可以进入 paper/live。

## 下一步建议

不要继续堆叠常见 EA 小变体。后续已完成多个 meta-only 约束：

- `execution_cost_floor_audit`：审计不同腿数、持有周期、入场频率下的最低可行收益门槛。
- `low_turnover_research_gate`：要求新方向预期持有至少 3 天、每月事件数不超过 12、月度执行成本不超过 10%。
- `no_trade_filter_research`：从已淘汰报告提取不交易状态候选，证据有限，仅作为线索。
- `okx_free_data_liquidity_map`：整理免费 OKX 数据覆盖与流动性分层。
- `rejected_strategy_failure_clusters`：聚类已淘汰策略失败原因。
- `frozen_family_reactivation_criteria`：约束冻结家族长期重启条件。
- `low_turnover_public_research_scan`：扫描未注册低换手公开方向。

下一步优先把 `no_trade_filter_research` 的证据扩大到更多 rejected 报告，或从低换手公开扫描中挑一个方向先写研究卡，但不得直接成为 candidate。

## 建议的并行分工

- Claude Code：可做 `no_trade_filter_research` 的报告层或低风险统计脚本。
- Gemini：可做免费 OKX 数据覆盖与流动性地图的只读审查。
- Codex：负责不交易过滤器核心审计、注册表、安全测试和后续方向判断。

## 验证与交接

- Claude 最近报告 `597 passed`；Codex 后续新增/修改登记与安全测试分别通过。
- 新会话开始后，应在所有代理改动汇合后重新运行一次完整 `python -m pytest`，确认最终总数。
- 使用 `research_approval_registry.py` 更新 `reports/research_approval_registry.json`，任何策略只有状态显式变为 `approved` 且 `eligible_for_paper=true` 才能解除运行时保护。
