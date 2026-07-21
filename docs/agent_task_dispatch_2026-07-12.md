# 多代理任务派发（2026-07-12）

## 总原则

当前没有任何策略获准模拟盘或实盘。所有代理都必须遵守：

- 不接入 `runner.py`；
- 不解除 `--enable-rule-strategies` 或 `--enable-pairs` 保护；
- 不修改 `approved_for_paper=[]` 与 `safe_to_enable_trading=false`；
- 不用 Binance 或其他交易所数据证明 OKX 可执行收益；
- 不用调参复活形成期失败的方向；
- 不执行 `git reset --hard`、`git checkout --` 或清理他人改动。

## Claude Code：低/中技术实现任务

### C1：F2 震荡行情内 Funding 异常事件审计

目标：把已经登记为 `pending` 的 F2 做成独立事件审计，不写策略。

允许新增文件：

- `range_regime_funding_extreme_audit.py`
- `tests/test_range_regime_funding_extreme_audit.py`
- `reports/range_regime_funding_extreme_audit.json`
- `docs/range_regime_funding_extreme_audit_2026-07-12.md`

可读取但避免修改：

- `regime_validation.py`
- `funding_rate.py`
- `docs/funding_extreme_range_regime_design_review_2026-07-12.md`
- `reports/research_approval_registry.json`

冻结规则：

- 只使用 OKX funding 与 OKX 15m OHLCV；
- 只在已完成 4h K 线标记为 `震荡` 的状态内统计；
- funding 异常必须使用每个币种自己的滚动分位数；
- 入场必须在 funding 结算确认后的下一根 15m；
- 每个行情层少于 15 个事件直接停止；
- 不改阈值重跑。

交付：

- 事件审计 JSON；
- 简短结论文档；
- 测试覆盖：滚动分位数无前视、震荡标签使用已完成 4h、下一根 15m 入场。

### C2：唐奇安 + ATR 趋势基准研究卡

目标：只写预注册研究卡，不写审计脚本。

允许新增文件：

- `docs/donchian_atr_trend_baseline_research_card.md`

要求：

- 把海龟、N 日高低点突破、通道突破、ATR 跟踪止损统一成一个代表家族；
- 只声明少量窗口，不列参数网格；
- 明确成本、入场语义、形成期/OOS 分割；
- 明确失败后不得改窗口、ATR 倍数、币种集合继续搜索。

## Gemini：文档和数据可行性任务

### G1：OKX 交割合约跨期价差免费数据可行性审查

目标：只做数据门审查，不下载付费数据，不写策略。

允许新增文件：

- `docs/okx_futures_calendar_spread_data_feasibility_2026-07-12.md`

要求：

- 确认 OKX 交割合约历史 K 线是否免费、公开、可复现；
- 确认是否能连续覆盖至少 365 天；
- 确认是否能和 OKX 永续/现货对齐；
- 列出换月、合约代码、交割日、手续费、滑点、完整腿数的研究风险；
- 如果免费数据不足，直接结论为 `data_blocked`，不得建议付费替代。

### G2：策略宇宙覆盖审查

目标：审查 `docs/strategy_universe_and_research_priorities_2026-07-12.md` 是否覆盖用户列出的常见 EA 家族。

允许新增文件：

- `docs/strategy_universe_gap_review_2026-07-12.md`

要求：

- 不新增策略批准；
- 只标记覆盖、合并、冻结或不适用；
- 不提出参数搜索计划；
- 对股票/ETF/财报/期权等非 OKX 永续方向标记为不适用或数据受阻。

## Codex：保留高判断任务

Codex 负责需要更高 agent 判断与系统集成的工作：

1. 研究批准登记维护：`research_approval_registry.py` 与机器可读 JSON；
2. 多代理产物合并审查，防止互相覆盖、重复研究或绕过安全闸门；
3. 前视偏差、成本遗漏、数据同源性、样本外污染审计；
4. 形成期失败后的淘汰决策；
5. 把通过文档审查的方向升级为事件审计，把失败方向登记为 `rejected`；
6. 长期研究框架与策略家族抽象，而不是单指标参数搜索。

## 当前 Codex 下一步

等待 Claude Code / Gemini 交付后，Codex 执行：

1. 审查新增报告是否满足预注册边界；
2. 必要时补测试；
3. 更新 `research_approval_registry.py`；
4. 重新生成 `reports/research_approval_registry.json`；
5. 运行完整 `python -m pytest`；
6. 更新总交接文档。

## 第一轮交付状态

- C1：已完成并由 Codex 修正口径后登记为 `rejected`。
- C2：已完成研究卡。
- G1：已完成，OKX 交割合约跨期价差由 `data_blocked` 调整为 `candidate`。
- G2：已完成，策略宇宙覆盖审查无新增缺口。

## 第二轮派发

### Claude Code C3：震荡内均值回归代表规则研究卡

目标：只写预注册研究卡，不写审计脚本，不接入策略。

允许新增文件：

- `docs/range_regime_mean_reversion_research_card.md`

要求：

- 用一个代表规则覆盖 RSI、KDJ、布林带反弹、BIAS、区间高抛低吸家族；
- 推荐代表规则为“震荡标签内布林带反弹”，但只能选一个代表，不写参数网格；
- 必须使用 `regime_validation.py` 的已完成 4h `震荡` 标签；
- 明确入场为信号确认后的下一根 15m 开盘；
- 明确成本至少 `0.16%` 往返；
- 明确形成期/OOS 分割；
- 明确形成期失败后不得调整 RSI/KDJ/布林倍数、窗口、币种集合、持有期或方向；
- 明确它不是策略，不能接入 `runner.py`。

禁止修改：

- `research_approval_registry.py`
- `reports/research_approval_registry.json`
- `runner.py`
- 任何已有审计报告

### Claude Code C4：UTC 时段突破研究卡

目标：只写预注册研究卡，不写审计脚本。

允许新增文件：

- `docs/utc_session_breakout_research_card.md`

要求：

- 把开盘区间突破、箱体突破、时间切片、funding 结算后窗口统一成一个代表家族；
- 固定少量 UTC 时段，不允许根据收益挑时段；
- 明确区间完成后下一根 15m 入场；
- 明确成本至少 `0.16%` 往返；
- 明确 15m OHLCV 同源 OKX 数据；
- 明确不使用 tick、盘口、逐笔成交，因为免费历史深度不足；
- 明确失败后不得改 UTC 窗口、区间长度、持有期、币种集合继续搜索。

禁止修改：

- `research_approval_registry.py`
- `runner.py`
- 任何策略实现文件

### Gemini G3：OKX 交割合约跨期价差数据管线研究卡

目标：在 G1 可行性结论基础上，只写“数据管线与拼接研究卡”，不写收益策略。

允许新增文件：

- `docs/okx_futures_calendar_spread_pipeline_research_card.md`

要求：

- 明确需要下载的 OKX 官方归档类型：FUTURES、SWAP、必要时 SPOT；
- 说明如何选择当季/次季/主力合约，如何处理合约代码生命周期；
- 明确换月规则，例如交割前至少 3 天强制换月；
- 明确拼接方式：不直接用拼接价格做技术指标，优先研究价差序列；
- 明确四腿成本至少 `0.32%`，并额外列出换月成本；
- 明确单腿成交风险、流动性枯竭、交割手续费风险；
- 输出“进入下载器实现前的验收清单”。

禁止修改：

- 下载器代码；
- `research_approval_registry.py`；
- `runner.py`；
- 任何报告 JSON。

### Gemini G4：外部事件/新闻/宏观方向冻结说明

目标：把宏观数据、新闻爬虫、舆情事件、财报等方向写成冻结说明，避免未来反复提出。

允许新增文件：

- `docs/external_event_news_macro_freeze_2026-07-12.md`

要求：

- 解释为什么这些方向当前不适合 OKX EA 研究；
- 核心理由：免费可复现历史数据库不足、发布时间对齐困难、前视偏差高、非 OKX 同源；
- 明确不禁止未来研究，但必须先满足 365 天免费公开可复现数据门；
- 不提出爬虫实现方案；
- 不提出付费数据方案；
- 不新增策略批准。

## 第二轮 Codex 保留任务

Codex 暂不派出以下任务：

1. 唐奇安 + ATR 趋势基准事件审计；
2. 所有研究登记状态更新；
3. 所有形成期失败判定；
4. 所有多代理交付合并审查；
5. 全量测试与交接文档更新。

理由：这些任务涉及入场时序、止损路径、形成期/OOS、成本口径、集中度和批准闸门，容易因细节错误制造假收益，需由 Codex 统一处理。

## 第二轮交付状态

- C3：已完成研究卡；Codex 审校后补充 4h 布林带与 ATR 只能使用已完成 4h K 线，避免 15m 入场偷看未完成 4h。
- C4：已完成研究卡；Codex 审校后修正为仅做多突破，并明确 UTC 04:15 只是最早可能入场时间，实际入场必须在突破确认后的下一根 15m。
- G3：已完成数据管线研究卡；状态保持 `candidate`，尚未允许下载器实现或收益策略。
- G4：已完成冻结说明；由 Codex 登记为外部事件/新闻/宏观 `frozen` 家族。

## Codex 执行状态

- 唐奇安 + ATR 趋势基准事件审计：已完成并登记为 `rejected`。形成期单月集中度 26.32% 超过预注册上限 25%，样本外扣成本净均值 -0.5898%。
- 震荡行情内均值回归事件审计：已完成并登记为 `rejected`。形成期 231 笔事件，扣成本净均值 -0.1230%，胜率 47.62%，盈利因子 0.8598。
- UTC 时段突破事件审计：已完成并登记为 `rejected`。形成期 3440 笔事件，扣成本净均值 -0.2059%，胜率 40.32%，盈利因子 0.7776。

## 第三轮背景

截至本轮派发前，所有候选收益策略已完成审计并淘汰。

当前注册表状态：

- `approved=0`
- `candidate=0`
- `rejected=15`
- `invalid=2`
- `risk_blocked=1`
- `frozen=2`
- `meta_only=3`
- `approved_for_paper=[]`
- `safe_to_enable_trading=false`

新增 meta-only 约束：

- `docs/execution_cost_floor_audit_2026-07-12.md`
- `reports/execution_cost_floor_audit.json`
- `docs/low_turnover_research_gate_2026-07-12.md`
- `reports/low_turnover_research_gate.json`

第三轮目标不是寻找新开仓信号，而是建立下一轮研究的禁区、数据地图与低换手候选框架。

## 第三轮总禁令

所有代理必须遵守：

- 不接入 `runner.py`。
- 不解除运行时保护。
- 不把任何方向改成 `approved` 或 `eligible_for_paper=true`。
- 不用调参复活已淘汰策略。
- 不写高频、网格、马丁、锁仓或亏损加仓策略。
- 不建议付费数据。
- 不用 Binance 证明 OKX 可执行收益。
- 不修改 `reports/research_approval_registry.json`，除非 Codex 明确要求。
- 不运行破坏性 git 命令。

## 第三轮 Claude Code 任务

### C5：不交易过滤器候选统计脚本

目标：实现一个只读统计脚本，研究“哪些市场状态最容易产生失败事件”，不产生交易信号。

允许新增文件：

- `no_trade_filter_research.py`
- `tests/test_no_trade_filter_research.py`
- `reports/no_trade_filter_research.json`
- `docs/no_trade_filter_research_2026-07-12.md`

建议输入：

- 已有 rejected 报告 JSON：
  - `reports/donchian_atr_trend_baseline_audit.json`
  - `reports/range_regime_mean_reversion_audit.json`
  - `reports/utc_session_breakout_audit.json`
  - `reports/range_regime_funding_extreme_audit.json`
  - `reports/okx_futures_calendar_spread_mean_reversion_audit.json`
- 可读取 `regime_validation.py`，但不要改。

要求：

- 汇总失败事件的月份集中度、持有期、胜率、净收益、退出原因。
- 如果报告里有 regime 字段，就按 regime 汇总；没有则标记 `regime_unavailable`。
- 输出“可能禁止交易状态”候选，例如高成本、高频、短持有、单月集中。
- 只输出过滤器候选，不得输出开仓规则。
- 不得把过滤器接入任何策略。

验收：

- 测试覆盖缺字段 JSON 的容错。
- 测试覆盖空事件报告。
- 测试覆盖高失败率状态被标记为 filter candidate。
- 全部新增文件自包含。

### C6：低换手候选研究卡模板

目标：写一个模板文档，规定未来低换手方向申请研究卡时必须填写哪些字段。

允许新增文件：

- `docs/low_turnover_research_card_template.md`

必须包含字段：

- 数据来源与免费可复现性。
- OKX 同源性说明。
- 预期持有周期，必须 >= 3 天。
- 预期每月事件数，必须 <= 12。
- 执行腿数与月度成本估计。
- 为什么不是已淘汰家族的小变体。
- 信息可用时间与下一根可成交价格。
- 形成期/OOS 切分。
- 失败后不得调整的参数清单。
- 明确“不允许直接接入 runner.py”。

禁止：

- 不写任何具体策略参数。
- 不推荐某个币。
- 不改注册表。

### C7：研究报告索引整理

目标：整理一份索引，把所有已完成研究报告按状态分类，方便后续 agent 查阅。

允许新增文件：

- `docs/research_report_index_2026-07-12.md`

要求：

- 按 `invalid`、`rejected`、`risk_blocked`、`frozen`、`meta_only` 分类。
- 每个条目列出研究 id、中文名、核心结论、证据路径。
- 数据来源以 `research_approval_registry.py` 或 `reports/research_approval_registry.json` 为准。
- 不新增解释性发挥，不改结论。

验收：

- 索引中必须写明 `approved=0`、`candidate=0`。
- 索引不得包含任何 `approved_for_paper` 条目。

### C8：只读测试卫生审查

目标：只读审查当前测试体系是否还存在“候选策略数量固定为 1”之类过时假设。

允许新增文件：

- `docs/test_hygiene_review_2026-07-12.md`

要求：

- 搜索测试里对 `candidate`、`approved_for_paper`、`safe_to_enable_trading`、`meta_only` 的断言。
- 只写审查报告，不改测试。
- 标记哪些断言是安全闸门，哪些是可能未来需要泛化的脆弱断言。

禁止：

- 不修改测试。
- 不运行全量测试；最多运行只读搜索命令。

## 第三轮 Gemini 任务

### G5：免费 OKX 数据覆盖与流动性地图审查

目标：只读文档审查，整理当前免费 OKX 数据的可研究范围。

允许新增文件：

- `docs/okx_free_data_liquidity_map_2026-07-12.md`

要求：

- 按数据类型分类：15m OHLCV、1m OHLCV、funding、日线 OI、FUTURES、SWAP、SPOT。
- 标出哪些已满足 365 天，哪些不足。
- 标出哪些适合收益审计，哪些只适合 meta-only。
- 明确 tick、盘口、逐笔成交、清算、期权历史深度不足。
- 不建议付费数据。

参考：

- `reports/research_data_gate_post_download.json`
- `docs/session_handoff_2026-07-12.md`
- `docs/research_universe_postmortem_and_next_direction_2026-07-12.md`

### G6：已淘汰策略失败原因聚类

目标：文档聚类，不写代码。

允许新增文件：

- `docs/rejected_strategy_failure_clusters_2026-07-12.md`

要求：

- 把 15 个 rejected 策略按失败原因聚类：
  - 成本吞噬
  - 样本外失败
  - 信息时序修复后失效
  - 样本不足
  - 事件集中度超标
  - 数据/微结构不可复现
- 每类列出代表策略和证据路径。
- 不能提出“调参再试”的建议。
- 结尾给出下一轮研究避坑规则。

### G7：冻结家族长期重启条件

目标：为 frozen/risk_blocked 家族写长期重启门槛，不写实现。

允许新增文件：

- `docs/frozen_family_reactivation_criteria_2026-07-12.md`

覆盖家族：

- 网格/马丁/锁仓/亏损加仓。
- 机器学习/动态路由。
- 外部事件/新闻/宏观。
- tick/盘口高频。
- 期权/波动率。

要求：

- 每类写“为什么当前冻结”。
- 每类写“未来满足什么条件才允许重新讨论”。
- 明确不得用付费数据绕过免费可复现门。
- 明确不得用模型调参制造 alpha。

### G8：低换手方向公开资料扫描

目标：只做资料级别扫描，找低换手 crypto/CTA 思路的公开、可复现研究方向，不批准策略。

允许新增文件：

- `docs/low_turnover_public_research_scan_2026-07-12.md`

要求：

- 只列方向，不写参数。
- 每个方向必须说明：
  - 可能的数据来源是否免费。
  - 预期持有周期是否 >= 3 天。
  - 为什么不同于已淘汰短线 EA。
  - 进入研究前还缺什么数据门。
- 不允许推荐付费论文、付费数据、付费信号。
- 不允许把方向标记为 approved/candidate。

## 第三轮 Codex 保留任务

Codex 保留以下高判断任务，不派发：

1. `no_trade_filter_research` 结果是否能进入注册表 `meta_only`。
2. 任何新低换手方向是否可成为 `candidate`。
3. 研究批准注册表更新。
4. 任何收益审计脚本。
5. 任何形成期/OOS 判定。
6. 全量测试和最终交接文档。

## 第三轮交付顺序建议

优先顺序：

1. Claude C7：研究报告索引。
2. Gemini G6：失败原因聚类。
3. Claude C5：不交易过滤器候选统计。
4. Gemini G5：免费数据覆盖地图。
5. Claude C6：低换手研究卡模板。
6. Gemini G7/G8：长期方向文档。
7. Claude C8：测试卫生只读审查。

理由：先整理事实，再做过滤器和未来方向，最后做测试卫生。
