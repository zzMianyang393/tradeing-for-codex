# 已淘汰策略失败原因聚类分析报告

**审查日期**：2026-07-12  
**仅新建**：`docs/rejected_strategy_failure_clusters_2026-07-12.md`  
**数据基础**：对注册表中 15 个被正式判定为 `rejected` 的策略进行失效归因与聚类。

---

## 一、失败原因聚类与代表策略

通过对已淘汰的 15 个策略进行深度审计，所有失效案例可归纳为以下六大 failure clusters：

### Cluster 1: 成本吞噬 (Cost Devouring / Friction)
这类策略在不计成本或使用极低费率假设时可能存在账面“正期望”，但在计入真实 OKX Taker 手续费（往返至少 0.10%）、真实滑点（单腿至少 0.03%）以及多腿摩擦后，期望值被完全打回负值。

- **代表策略 1**：`spot_perp_basis`（期现基差套利）
  - *失效表现*：基差的均值回复波幅极窄（95分位仅为 +2.1bp），远远无法覆盖四腿交易（现货买卖+永续买卖）合计约 **0.28% - 0.32%** 的硬性摩擦成本。
  - *证据路径*：`reports/okx_basis_audit.json`，`reports/basis_microstructure_audit.json`
- **代表策略 2**：`okx_futures_calendar_spread`（OKX 交割合约跨期价差）
  - *失效表现*：价差虽有回归特征，但在扣除四腿往返成本（建仓2腿+平仓2腿，合计配置为 **0.32%**）后，形成期净均值（`-0.0938%`）与样本外净均值（`-0.0615%`）双侧皆负。
  - *证据路径*：`reports/okx_futures_calendar_spread_mean_reversion_audit.json`
- **代表策略 3**：`btc_alt_lead_lag`（BTC 对非 BTC 短时领先滞后）
  - *失效表现*：短线领先滞后的冲击幅度过小，扣除 15m 的 Taker 手续费与执行滑点后，在形成期即录得净负期望。
  - *证据路径*：`reports/btc_alt_lead_lag_formation.json`
- **代表策略 4**：`multi_coin_funding_crowding`（多币种资金费率拥挤反转）
  - *失效表现*：多币种资金费率在结算时的溢价反转无法提供足够的波动空间来覆盖单次 15m 往返的 0.16% 交易成本。
  - *证据路径*：`reports/multi_coin_funding_crowding_audit.json`

---

### Cluster 2: 信息时序修复后失效 (Information/Timing Correction Failure)
这类策略此前的“高收益报告”建立在使用了不正确的可用时间假设（前视偏差）之上。在被强制修正入场时序（即信号确认后延迟到下一个可成交 K 线）后，期望值立即转负。

- **代表策略 5**：`funding_oi_time_corrected`（Funding 与 OI 联合信号时间修复版）
  - *失效表现*：原始报告将当天的日线 OI 提前到 00:00 提取，构成了前视偏差。修复为“日线 OI 只能在 16:00 UTC 以后可见，最早 16:15 UTC 入场”后，策略在形成期 4h 的净均值转为 `-0.74%`，且多币种方向彻底发生背离。
  - *证据路径*：`reports/funding_oi_trend_confirmation_repaired.json`

---

### Cluster 3: 样本外失败 (Out-of-Sample Failure)
这类策略在形成期（In-Sample）展示了优秀的均值和胜率，但在跨越时间窗口、进入未被模型“看见”的样本外（Out-of-Sample）区间后，期望值迅速衰减甚至大幅亏损。

- **代表策略 6**：`relative_strength_persistence`（相对强弱持续）
  - *失效表现*：在形成期表现出强势币种动量延续，但进入样本外后，由于市场风格快速轮动，高位追强的策略遭遇高额滑点与反转踩踏，样本外大幅亏损。
  - *证据路径*：`reports/rs_persistence_entry_timing_audit.json`
- **代表策略 7**：`pairs_walk_forward`（配对统计套利）
  - *失效表现*：大量币对在 IS 形成期看似具备显著的协整关系，但在 OOS 样本外发生协整关系破裂（Co-integration Drift），无任何一对能通过多重多重检验门槛。
  - *证据路径*：`reports/pairs_walk_forward_v1.json`
- **代表策略 8**：`daily_oi_independent_change`（日线 OI 独立变化率）
  - *失效表现*：在形成期表现出微弱的单向概率，但在样本外阶段 4h 做多与做空双侧均录得扣成本后净亏损。
  - *证据路径*：`reports/daily_oi_independent_change_audit.json`
- **代表策略 9**：`range_regime_mean_reversion_family`（震荡行情内均值回归家族）
  - *失效表现*：形成期 231 笔事件扣成本后净均值为 `-0.1230%`，胜率仅 `47.62%`，宣告失效。
  - *证据路径*：`reports/range_regime_mean_reversion_audit.json`
- **代表策略 10**：`utc_session_breakout_family`（UTC 时段开盘区间突破家族）
  - *失效表现*：由于突破后极易发生假突破回归，扣成本后净均值录得 `-0.2059%`，胜率 `40.32%`。
  - *证据路径*：`reports/utc_session_breakout_audit.json`
- **代表策略 11**：`btc_trend_pullback`（BTC 趋势内山寨回调）
  - *失效表现*：即使在预先标记的趋势上行区间，回调买入依然发生均值回归偏移，整体录得净亏损。
  - *证据路径*：`reports/btc_trend_pullback_regime_formation.json`

---

### Cluster 4: 样本不足 (Insufficient Sample / Event Count)
这类策略由于触发条件过于严苛，在整整 365 天或更长周期内仅能提供寥寥几个事件，无法形成稳定的统计学显著性，或者策略被迫因样本量低于 15 个的门槛而自动中止。

- **代表策略 12**：`vol_compression_breakout`（波动率压缩突破）
  - *失效表现*：布林带收窄至极端低波动率的状态极少发生，全年在多币种下也未凑齐 15 个有效事件，不具备大样本统计验证基础。
  - *证据路径*：`reports/vol_compression_breakout_entry_timing_audit.json`
- **代表策略 13**：`positive_funding_carry`（正资金费率市场中性持有）
  - *失效表现*：要求资金费率保持高水平且价差具备套利空间的合格事件在形成期数量归零。
  - *证据路径*：`reports/funding_carry_formation.json`

---

### Cluster 5: 事件集中度超标 (Event Concentration Violation)
这类策略表面上的正收益并非来自于信号的普适有效性，而是由于极少数时间窗内发生的重大宏观行情（如特朗普当选、减半暴涨等）强行拉高了均值，构成“幸存者偏差”。

- **代表策略 14**：`donchian_atr_trend_baseline`（唐奇安通道 + ATR 趋势基准）
  - *失效表现*：形成期表现看似达标，但深入审计发现其单月事件集中度高达 **26.32%**（超过 25% 的安全上限），且正收益完全由 2024 年 11 月的单边大牛市主导，一旦进入正常的样本外区间，期望值立刻崩溃至 `-0.5898%`。
  - *证据路径*：`reports/donchian_atr_trend_baseline_audit.json`
- **代表策略 15**：`range_regime_funding_extreme`（震荡行情内 Funding 异常）
  - *失效表现*：形成期事件分布在单月集中度超过 **30%**，严重违反了事件分布均匀性的预注册要求。
  - *证据路径*：`reports/range_regime_funding_extreme_audit.json`

---

### Cluster 6: 数据/微结构不可复现 (Data Non-reproducibility)
此类虽然在某些外部平台（如 Binance 或 TradingView 的历史回放）上录得收益，但在 OKX 真实微结构（如滑点、深度、结算频率）下完全无法复现，已被硬性拒绝。
- *(注：该类主要是 Binance OI / Binance 多空比等研究代理，因不具备 OKX 同源执行兼容性，在第一关数据门审计中即被排除。)*

---

## 二、下一轮研究避坑规则（Avoidance Rules）

为了不重复掉进上述已证伪的深坑中，未来的量化研究必须严格遵守以下防守型约束：

1. **“双腿”套利策略死守 0.32% 成本底线**：任何涉及现货-永续、永续-交割、交割-交割的两合约价差策略，回测的往返成本必须写死为 **0.32%**。凡是价差波幅均值低于 0.35% 的方向直接拉黑，禁止立项。
2. **信号时序在代码层硬约束**：凡是引入日线数据、资金费率、大户多空比等事件型指标，数据读取函数必须显式加入延迟逻辑（如日线 OI 在当天 16:00 UTC 之前设为 NaN）。
3. **严格遵守集中度限制（< 25%）**：策略的事件分布必须通过集中度审计，任何在单月集中度超过 25% 的策略，即使均值再高，也必须被视作“幸存者偏差”而直接淘汰。
4. **低换手率硬防线**：拒绝短线剥头皮或频繁翻仓的策略。新方向预期持有周期必须 **$\ge 3$天**，且月度交易频率受限，以防止策略最终沦为给交易所“打工”的送手续费机器。

---
*本报告遵循只读原则，未对测试或策略引擎做出任何代码改动。*
