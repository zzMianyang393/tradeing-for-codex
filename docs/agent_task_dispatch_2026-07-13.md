# Agent Task Dispatch（2026-07-13）

## 共同目标

建立“组合特征池”研究层。已淘汰单策略可以重新进入组合研究，但只能作为特征、状态标签或弱信号重新审计；不得以原策略身份复活，不得进入 paper trading，不得接入 runner.py。

当前硬约束：

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- 单策略 `rejected` 不等于永久无价值，但仍不得单独交易。
- `invalid`、`risk_blocked`、`data_blocked` 不得进入组合方向性信号池。
- 网格、马丁、锁仓、亏损加仓类永久禁止借组合名义复活。
- OI/杠杆状态只能作为 context/meta label，不得单独方向开仓。

建议新增状态语义：

| 状态 | 含义 |
|---|---|
| feature_pool_eligible | 单策略不可交易，但可作为组合层特征/弱信号重新审计 |
| feature_pool_blocked | 单策略淘汰且不适合进入组合特征池 |
| meta_feature_only | 只能作为状态标签、过滤器候选或风险上下文 |

---

## ClaudeCode 任务

### C14：组合特征池 Schema 与生成器

交付：

- 新建 `strategy_feature_pool.py`
- 新建 `reports/strategy_feature_pool.json`
- 新建 `tests/test_strategy_feature_pool.py`

要求：

- 从 `reports/research_approval_registry.json`、`reports/strategy_preflight_review.json` 和现有 audit 报告中生成组合特征池。
- 每个 feature 至少包含：
  - `feature_id`
  - `source_research_id`
  - `source_status`
  - `feature_role`: `directional_weak_signal` / `context_label` / `risk_filter_candidate` / `blocked`
  - `allowed_in_combo_research`
  - `allowed_as_standalone_strategy`
  - `eligible_for_paper`
  - `block_reasons`
  - `evidence_paths`
- 强制断言：
  - `allowed_as_standalone_strategy = false` 对所有 feature 成立。
  - `eligible_for_paper = false` 对所有 feature 成立。
  - `invalid` 研究不得进入 `directional_weak_signal`。
  - `risk_blocked` 研究不得 `allowed_in_combo_research=true`。
  - `daily_bb_mean_revert` 可进入 `directional_weak_signal`，但必须标注 `concentration_risk`。
  - `daily_ma_alignment` 可进入 `context_label` 或 `directional_weak_signal`，但必须标注 `insufficient_events` 和 `no_oos_entries`。
  - `oi_deleveraging_filter` 只能进入 `context_label` 或 `risk_filter_candidate`，不得方向开仓。

验收：

- 新增测试不少于 12 个。
- 不修改 `runner.py`、`executor.py`、实盘配置。
- 全量相关测试通过。

### C15：组合特征池预检器

交付：

- 新建 `feature_pool_preflight_review.py`
- 新建 `reports/feature_pool_preflight_review.json`
- 新建 `docs/feature_pool_preflight_review_2026-07-13.md`
- 新建 `tests/test_feature_pool_preflight_review.py`

要求：

- 读取 `reports/strategy_feature_pool.json`。
- 输出以下分组：
  - `directional_feature_candidates`
  - `context_label_candidates`
  - `risk_filter_candidates`
  - `blocked_features`
- 阻断规则：
  - `invalid`、`data_blocked`、`risk_blocked` 默认 blocked。
  - 四腿套利类如果失败原因为成本吞噬，默认 blocked，不进入方向池。
  - 单月正收益贡献超标的 feature 可进入组合池，但必须带 `requires_concentration_penalty=true`。
  - 样本外为空的 feature 不得作为方向信号，只能作为 context label，除非文档明确说明是状态标签。

验收：

- `approved_for_paper` 仍为空。
- `safe_to_enable_trading` 仍为 false。
- 不新增任何交易策略入口。

### C16：组合研究安全闸门测试

交付：

- 扩展或新建 `tests/test_combo_research_safety.py`

要求：

- 断言组合研究代码不得导入或调用 `runner.py` 的交易执行入口。
- 断言 feature pool 中任何 item 都不能 `eligible_for_paper=true`。
- 断言 `grid_martingale_locking_family` 不得进入任何候选池。
- 断言 `funding_oi_joint_original` 这类 invalid 只能 blocked。
- 断言 feature pool 是研究层，不是策略层。

验收：

- 测试命名清楚，不依赖外部网络。

### C17：组合层研究卡模板

交付：

- 新建 `docs/combo_strategy_research_card_template_2026-07-13.md`

要求：

- 明确组合策略开题前必须预注册：
  - 特征列表
  - 权重方式
  - 是否允许方向信号投票
  - 是否允许 context filter
  - 成本模型
  - 月度集中度惩罚
  - OOS 窗口
  - 特征相关性上限
  - 禁止调参规则
- 明确组合策略不得改变原始 feature 的历史信号定义。

---

## Gemini 任务

### G14：已淘汰策略作为组合特征的语义复核

交付：

- 新建 `docs/rejected_strategy_feature_reuse_review_2026-07-13.md`

要求：

- 审查所有 `rejected` 策略，按以下分类：
  - 可作为方向弱信号
  - 只能作为 context label
  - 只能作为 risk/no-trade candidate
  - 不可复用
- 对每个策略说明原因。
- 特别复核：
  - `daily_bb_mean_revert`
  - `daily_ma_alignment`
  - `daily_low_turnover_momentum`
  - `donchian_atr_trend_baseline`
  - `range_regime_mean_reversion_family`
  - `utc_session_breakout_family`
  - `funding_term_carry`
  - `multi_coin_funding_crowding`
  - `spot_perp_basis`
  - `pairs_walk_forward`

禁止：

- 不得建议把任何 rejected 策略直接恢复为独立策略。
- 不得建议 paper trading。

### G15：100+ 原型组合复用地图

交付：

- 新建 `docs/prototype_universe_combo_reuse_map_2026-07-13.md`

要求：

- 基于 `docs/strategy_prototype_universe_100_draft_2026-07-13.md`。
- 不要求改代码。
- 给 100+ 原型打组合复用标签：
  - `directional_feature_candidate`
  - `context_feature_candidate`
  - `risk_filter_candidate`
  - `blocked_from_combo`
  - `duplicate_needs_mapping`
- 标出需要 ClaudeCode 后续结构化接入的前 30 个原型。

### G16：组合策略常见失真风险清单

交付：

- 新建 `docs/combo_strategy_bias_risk_review_2026-07-13.md`

要求：

- 聚焦多弱策略组合的常见陷阱：
  - 多重检验
  - 特征共线性
  - 单月贡献集中
  - 使用 OOS 结果反向调权
  - 幸存者偏差
  - 成本叠加
  - 信号重叠导致实际换手翻倍
  - 把风控过滤器误当 alpha
- 输出必须转成后续工程可测试规则。

### G17：组合层准入门槛建议

交付：

- 新建 `docs/combo_research_admission_criteria_2026-07-13.md`

要求：

- 给出组合层开题门槛建议：
  - 最少 feature 数
  - 每个 feature 最少事件数
  - OOS 覆盖要求
  - 特征相关性上限
  - 单月贡献上限
  - 每月换手上限
  - 权重冻结规则
- 明确哪些门槛是硬规则，哪些只是观察指标。

---

## Codex 当前自留任务

### X14：状态体系仲裁

我负责：

- 审查 ClaudeCode 的 feature pool schema 是否过度放宽。
- 决定哪些 rejected 策略允许进入 feature pool。
- 明确 `feature_pool_eligible` 与 `eligible_for_research` 的边界。
- 保证 `approved_for_paper=[]` 和 `safe_to_enable_trading=false` 不被破坏。

### X15：第一版组合研究方向

我负责在 C14-C17、G14-G17 完成后制定第一版组合研究卡。默认方向不是立即回测组合，而是先做：

- feature 时间序列抽取规范
- feature 相关性矩阵
- 月度贡献归因
- 成本叠加模型
- no-trade/context label 的单独评估

---

## 当前不做

- 不接入 runner.py
- 不做 paper trading
- 不做实盘
- 不把 rejected 单策略改成 approved
- 不用组合名义复活马丁、网格、锁仓
- 不引入付费数据
- 不根据 OOS 表现反向调参
