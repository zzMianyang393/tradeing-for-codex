# 已淘汰策略作为组合特征的语义复核报告 (G14)

**文档日期**：2026-07-13  
**文档路径**：`docs/rejected_strategy_feature_reuse_review_2026-07-13.md`  
**基准决策约束**：  
- `approved_for_paper = []`  
- `safe_to_enable_trading = false`  
- **安全红线**：严禁将任何已淘汰单策略恢复为独立交易策略，组合特征池仅限作为只读特征，不得用于发起任何独立的 paper trading 仓位或实盘。

---

## 一、概述

组合策略研究的核心在于将多个历史策略转化为**只读特征（Features）或状态标签（Labels）**，以投票和风险控制的形式进行融合。为了规避“数据挖掘二次过拟合”和“换壳复活”的风险，本报告对注册表中所有 `status = rejected` 的策略进行逐一的语义复核。

所有策略的复用分类必须严格限定在以下四种角色之内：
- **`directional_feature_candidate`**：可作为方向弱信号投票特征，但绝不能独立交易。
- **`context_feature_candidate`**：仅能作为市场环境或状态分类标签，不产生方向投票。
- **`risk_filter_candidate`**：仅能作为拦截开仓的风险过滤器或不交易（No-Trade）候选。
- **`blocked_from_combo`**：不能进入特征池，在组合层也必须硬性阻断。

---

## 二、16 个重点淘汰策略语义复核明细

以下对指定的 16 个重点淘汰策略进行逐一审查，明确其推荐分类、推荐原因，并与 `feature_pool_preflight_review` 的预检结果进行比对判定：

### 1. `daily_bb_mean_revert` (日线布林带均值回复)
- **推荐分类**：`directional_feature_candidate`
- **推荐原因**：在形成期与样本外扣成本后均获得正收益，但其收益分布极度不均匀，严重依赖 2024-11 单月收益（占比 $63.49\%$）。因此不能独立交易。但在组合中，其可以作为一个弱的均值回复方向因子。
- **预检核对**：**同意**（当前预检分类为 `directional_feature_candidates`，并标注了集中度惩罚）。

### 2. `daily_ma_alignment` (日线均线多头排列趋势)
- **推荐分类**：`context_feature_candidate`
- **推荐原因**：形成期仅触发 3 笔事件，样本外为 0，属于极度稀疏事件。若作为方向性投票会导致样本严重不足而失真。应当退化为大周期多头排列状态的静态分类器特征。
- **预检核对**：**同意**（当前预检分类为 `context_label_candidates`，且警告标明因空 OOS 降级）。

### 3. `daily_low_turnover_momentum` (日线低换手 90日动量)
- **推荐分类**：`directional_feature_candidate`
- **推荐原因**：属于山寨币横截面动量，虽然 standalone 回测因为杠杆和单币种假突破亏损，但在横截面币种轮动打分中，可以有效提供币种相对强弱的方向性投票。
- **预检核对**：**同意**（当前预检分类为 `directional_feature_candidates`）。

### 4. `donchian_atr_trend_baseline` (唐奇安通道 + ATR 趋势基准)
- **推荐分类**：`directional_feature_candidate`
- **推荐原因**：经典的中长期低换手趋势跟踪特征。作为单策略在震荡盘整市中假突破流血过多，但可作为组合的趋势基础投票方向。
- **预检核对**：**同意**（当前预检分类为 `directional_feature_candidates`，且标注了集中度惩罚）。

### 5. `range_regime_mean_reversion_family` (震荡行情内均值回归家族)
- **推荐分类**：`risk_filter_candidate`
- **推荐原因**：在 15m 级别的布林或 ATR 边界逆势开仓胜率低于 $55\%$，扣成本后为纯负期望。它绝对不能发出交易方向投票，但其震荡边界发散的状态可以用于组合的 `no_trade_filter`，拦截趋势策略在盘整区的假突破。
- **预检核对**：**同意**（当前预检分类为 `risk_filter_candidates`）。

### 6. `utc_session_breakout_family` (UTC 时段开盘区间突破家族)
- **推荐分类**：`blocked_from_combo`
- **推荐原因**：日内高频（15m/1m）开盘突破策略。胜率低于 $45\%$，且频繁的虚假突破会导致交易次数激增， taker 手续费和滑点硬地板（双边 $0.16\%$）会吞噬任何潜在收益，在组合中也只会充当垃圾噪音，必须彻底封禁。
- **预检核对**：**同意**（当前预检分类为 `blocked_features`）。

### 7. `funding_term_carry` (中周期 Funding Term Carry)
- **推荐分类**：`context_feature_candidate`
- **推荐原因**：中周期利差对冲的期望收益无法覆盖 4 腿往返的 $0.32\%$ 摩擦成本。不能作为 Carry 方向性信号。但费率的滚动均值能极好地反映市场处于多头杠杆拥挤还是恐慌抛售状态。
- **预检核对**：**同意**（当前预检分类为 `context_label_candidates`）。

### 8. `multi_coin_funding_crowding` (多币种资金费率拥挤反转)
- **推荐分类**：`risk_filter_candidate`
- **推荐原因**：费率极值点的反转路径无法覆盖 taker 交易成本。仅能用作“高危杠杆拥挤”过滤器，在此状态下强行拦截同方向的趋势做多信号。
- **预检核对**：**同意**（当前预检分类为 `risk_filter_candidates`）。

### 9. `spot_perp_basis` (期现基差套利)
- **推荐分类**：`blocked_from_combo`
- **推荐原因**：现永基差极小，而 OKX Taker 模式下的期现对冲往返共 4 腿硬摩擦达 $0.32\%$。该硬性成本在组合中无法稀释，无任何复用价值。
- **预检核对**：**同意**（当前预检分类为 `blocked_features`）。

### 10. `pairs_walk_forward` (配对统计套利)
- **推荐分类**：`blocked_from_combo`
- **推荐原因**：基于 15m 的多币对协整和 Z-Score 均值回归在 OOS 中由于协整关系快速发散失效而带来巨大亏损。为防止研究人员利用 IS 拟合制造漂亮的伪曲线，禁止其作为组合特征。
- **预检核对**：**同意**（当前预检分类为 `blocked_features`）。

### 11. `okx_futures_calendar_spread` (OKX 交割合约跨期价差)
- **推荐分类**：`blocked_from_combo`
- **推荐原因**：预注册的交割跨期均值回归策略在扣除 $0.32\%$ 的双开双平 4 腿摩擦成本后，IS 和 OOS 净收益均呈现纯负。属于硬成本吞噬策略，永久禁用。
- **预检核对**：**同意**（当前预检分类为 `blocked_features`）。

### 12. `positive_funding_carry` (正资金费率市场中性持有)
- **推荐分类**：`blocked_from_combo`
- **推荐原因**：费率收益无法覆盖套利对冲的 4 腿交易滑点与 taker 手续费。
- **预检核对**：**同意**（当前预检分类为 `blocked_features`）。

### 13. `btc_alt_lead_lag` (BTC 对非 BTC 短时领先滞后)
- **推荐分类**：`blocked_from_combo`
- **推荐原因**：领先滞后特征在扣除手续费后呈现纯负期望，换手率极高，变相大幅放大了组合的执行摩擦。
- **预检核对**：**同意**（当前预检分类为 `blocked_features`）。

### 14. `funding_oi_time_corrected` (Funding 与 OI 联合信号 时间修复版)
- **推荐分类**：`context_feature_candidate`
- **推荐原因**：在剔除 16小时 前视偏差后，其真实的形成期净收益转负。不可做方向性信号。但由于其计算了 Funding Rate 和持仓量（OI）的联合变化，可以作为极佳的多空主力加仓状态环境标签。
- **预检核对**：**同意**（当前预检分类为 `context_label_candidates`）。

### 15. `range_regime_funding_extreme` (震荡行情内 Funding 异常)
- **推荐分类**：`risk_filter_candidate`
- **推荐原因**：在震荡区内，费率极值开仓胜率低于 $55\%$ 且月度集中度超过 $30\%$，扣成本后净均值为负。应作为风险拦截标签，在震荡市中对异常费率的代币进行避险拦截。
- **预检核对**：**同意**（当前预检分类为 `risk_filter_candidates`）。

### 16. `daily_oi_independent_change` (日线 OI 独立变化率)
- **推荐分类**：`context_feature_candidate`
- **推荐原因**：独立的持仓变化开仓胜率不足，但持仓量大幅波动代表了机构资金流向的 Regime 转换。可作为组合的持仓量状态标签（如 `is_oi_accumulation`）。
- **预检核对**：**同意**（当前预检分类为 `context_label_candidates`）。

---

## 三、专项约束分类清单

### 1. 绝对不能借组合名义复活的策略 (Strict Rejection List)
以下策略由于尾部风险超标、数据不完整、前视偏差污染或硬性交易成本超限，**绝对禁止**参与任何组合投票或提供状态特征：
*   **网格、马丁、锁仓加仓类 (`grid_martingale_locking_family`)**：因用尾部风险换取平滑净值，一票否决。
*   **存在前视偏差的 Invalid 策略**：`legacy_dynamic_router` 与 `funding_oi_joint_original`。其底层数据因未来信息被提前使用而受污染，禁止任何引用。
*   **高换手/多腿成本吞噬策略**：`spot_perp_basis` (期现基差)、`okx_futures_calendar_spread` (交割跨期价差)、`positive_funding_carry` (正费率持有)、`btc_alt_lead_lag` (领先滞后)、`utc_session_breakout_family` (UTC 突破)。无论怎么组合，taker 费用与滑点硬地板都无法稀释。

### 2. 可以保留但必须加集中度惩罚的策略 (Concentration Penalized List)
以下特征虽然被允许作为 `directional_feature_candidate` 参与组合投票，但鉴于其历史收益高度集中于 2024-11 单月牛市行情，工程回测中必须**强制开启 `requires_concentration_penalty = true`** 并在去除 2024-11 后进行对照审计：
*   `daily_bb_mean_revert` (日线布林带均值回复)
*   `donchian_atr_trend_baseline` (唐奇安通道 + ATR 趋势基准)
*   `daily_low_turnover_momentum` (日线低换手 90日动量)

### 3. 只能作为 Context 或 Risk Filter，不能做方向信号的策略 (Meta-only List)
以下特征由于胜率低、期望收益薄、或数据稀疏，**严禁产生多空方向性开仓投票**，仅允许用于仓位缩放或开仓拦截：
*   **环境标签 (Context Feature Candidates)**：
    *   `daily_ma_alignment` (均线排列，事件稀疏)
    *   `funding_term_carry` (中周期费率，无利差空间，仅作杠杆热度标签)
    *   `funding_oi_time_corrected` (修正后的费率/持仓量联合状态)
    *   `daily_oi_independent_change` (持仓独立变化)
    *   `relative_strength_persistence` (强弱动量环境)
*   **风险过滤器 (Risk Filter Candidates)**：
    *   `range_regime_mean_reversion_family` (拦截震荡假突破)
    *   `multi_coin_funding_crowding` (拦截费率过热点)
    *   `range_regime_funding_extreme` (震荡期费率异常拦截)
    *   `oi_deleveraging_filter` (去杠杆踩踏拦截)

---

## 四、结论

综上所述，当前预检报告 `feature_pool_preflight_review` 实施的分类拦截完全正确，符合本项目的物理成本和防前视偏差合同。特征池的只读研究层边界坚固，特征分类无一偏离，可安全地提交给后续分析阶段。
