# 100+ 原型组合复用地图 (G15)

**文档状态**：仅新建  
**文档路径**：`docs/prototype_universe_combo_reuse_map_2026-07-13.md`  
**基准约束**：  
- `approved_for_paper = []`  
- `safe_to_enable_trading = false`  
- **纪律红线**：所有原型在组合中仅允许作为只读特征或过滤器，严禁将组合特征作为独立策略开仓或进入 paper trading。

---

## 一、组合复用标签体系说明

为了将 111 个策略原型系统地映射进组合层特征池（Feature Pool），我们定义了以下五种分类标签：

1. **`directional_feature_candidate` (方向性特征候选)**  
   - **定义**：可用于计算币种相对强弱排名、多空投票分数的只读特征。
   - **约束**：在组合中不单独触发开仓，必须与其他特征融合。
2. **`context_feature_candidate` (状态环境特征候选)**  
   - **定义**：用于区分市场状态（如波动率高低、是否单边趋势排列、大盘主导度）的上下文特征。
3. **`risk_filter_candidate` (风险过滤器候选)**  
   - **定义**：在特定高风险窗口期（如周末、费率极端拥挤期、去杠杆踩踏期）强行拦截开仓的过滤器。
4. **`blocked_from_combo` (组合禁用)**  
   - **定义**：因包含前视偏差（Invalid）、马丁/网格高尾部风险（Risk Blocked）、外部数据缺失（Data Blocked）等原因而永久禁止接入组合的策略原型。
5. **`duplicate_needs_mapping` (重复且需映射至已有研究)**  
   - **定义**：该原型与现有注册表中已淘汰的 17 个策略或 10 个已审计元策略高度重复，必须强制映射到特定研究 ID，继承其所有的限制条件（如集中度惩罚）。

---

## 二、111 个原型的组合复用分类地图

### 1. 趋势跟踪家族 (TF_01 - TF_10)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **TF_01** | Donchian 55突破 | `directional_feature_candidate` | 中长期趋势基准 |
| **TF_02** | Donchian 20突破 | `duplicate_needs_mapping` | 映射至 `vol_compression_breakout` |
| **TF_03** | 均线 50/200 交叉 | `directional_feature_candidate` | 趋势多空状态投票 |
| **TF_04** | MACD 动量 | `directional_feature_candidate` | 价格动量变化率 |
| **TF_05** | ADX 趋势强度 | `context_feature_candidate` | 趋势环境过滤，不作方向投票 |
| **TF_06** | Parabolic SAR | `directional_feature_candidate` | 趋势止损转向特征 |
| **TF_07** | Keltner Channel Trend | `directional_feature_candidate` | 波动率通道突破 |
| **TF_08** | Ichimoku Cloud Trend | `directional_feature_candidate` | 云图大周期支撑特征 |
| **TF_09** | Linear Regression Slope | `context_feature_candidate` | 线性回归斜率环境分类 |
| **TF_10** | SuperTrend | `directional_feature_candidate` | 动态多空转折特征 |

### 2. 均值回归家族 (MR_01 - MR_10)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **MR_01** | 布林带均值回复 | `duplicate_needs_mapping` | 映射至 `daily_bb_mean_revert` |
| **MR_02** | RSI 超买超卖 | `duplicate_needs_mapping` | 映射至 `range_regime_mean_reversion_family` |
| **MR_03** | 随机指标反转 | `duplicate_needs_mapping` | 映射至 `range_regime_mean_reversion_family` |
| **MR_04** | CCI 极值反转 | `duplicate_needs_mapping` | 映射至 `range_regime_mean_reversion_family` |
| **MR_05** | RSI 背离反转 | `directional_feature_candidate` | 需低换手背离特征，过滤短线噪音 |
| **MR_06** | 均线极端偏离回归 | `directional_feature_candidate` | 乖离率特征，高换手需加惩罚 |
| **MR_07** | 枢轴点反弹 | `risk_filter_candidate` | 仅作为静态阻力/支撑位过滤器 |
| **MR_08** | 箱体震荡均值回归 | `duplicate_needs_mapping` | 映射至 `range_regime_mean_reversion_family` |
| **MR_09** | 波动率通道边界反弹 | `risk_filter_candidate` | 通道极值，用于拦截强趋势追多空 |
| **MR_10** | 威廉指标极值反转 | `duplicate_needs_mapping` | 映射至 `range_regime_mean_reversion_family` |

### 3. 突破家族 (BO_01 - BO_10)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **BO_01** | 通道高低点突破 | `directional_feature_candidate` | 经典突破特征 |
| **BO_02** | 布林带收口挤压突破 | `duplicate_needs_mapping` | 映射至 `vol_compression_breakout` |
| **BO_03** | ATR 波动率通道突破 | `directional_feature_candidate` | 价格伴随波动率放大突破 |
| **BO_04** | 放量确认突破 | `directional_feature_candidate` | 结合 Volume 的突破投票 |
| **BO_05** | UTC 开盘区间突破 | `duplicate_needs_mapping` | 映射至 `utc_session_breakout_family` |
| **BO_06** | K线收盘盘整区间突破 | `directional_feature_candidate` | 低频收盘价突破特征 |
| **BO_07** | 动量加速确认突破 | `directional_feature_candidate` | 结合 ROC 动量的突破 |
| **BO_08** | RSI/ squeeze 联合突破 | `directional_feature_candidate` | 强趋势区间内的动量突破 |
| **BO_09** | 波动率扩张突破 | `directional_feature_candidate` | 映射至 `vol_compression_breakout` |
| **BO_10** | 均线织带发散突破 | `directional_feature_candidate` | MA Ribbon 发散特征 |

### 4. 动量与轮动家族 (MO_01 - MO_10)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **MO_01** | RSI 强度横截面动量 | `duplicate_needs_mapping` | 映射至 `relative_strength_persistence` |
| **MO_02** | ROC 变化率动量排序 | `directional_feature_candidate` | 横截面强弱排序投票 |
| **MO_03** | 90日横截面动量 | `duplicate_needs_mapping` | 映射至 `daily_low_turnover_momentum` |
| **MO_04** | 120日横截面动量 | `duplicate_needs_mapping` | 映射至 `daily_low_turnover_momentum` |
| **MO_05** | BTC 领先滞后动量 | `duplicate_needs_mapping` | 映射至 `btc_alt_lead_lag` |
| **MO_06** | 量价权重动量 | `directional_feature_candidate` | 结合成交量的强弱动量 |
| **MO_07** | Alpha/Beta 轮动特征 | `directional_feature_candidate` | 根据对大盘的超额收益进行轮动 |
| **MO_08** | 指数回归拟合动量 | `directional_feature_candidate` | 拟合斜率排序，较平滑的动量特征 |
| **MO_09** | Chande 动量振荡器 | `directional_feature_candidate` | CMO 强度投票 |
| **MO_10** | 板块联动相关性动量 | `directional_feature_candidate` | 根据山寨币板块共振情况轮动 |

### 5. 资金费率与 Carry 家族 (FC_01 - FC_08)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **FC_01** | 现永费率套利 | `duplicate_needs_mapping` | 映射至 `positive_funding_carry` |
| **FC_02** | 7日费率 Term Carry | `duplicate_needs_mapping` | 映射至 `funding_term_carry` |
| **FC_03** | 14日费率 Term Carry | `duplicate_needs_mapping` | 映射至 `funding_term_carry` |
| **FC_04** | 震荡行情费率极值回归 | `duplicate_needs_mapping` | 映射至 `range_regime_funding_extreme` |
| **FC_05** | 多币种费率拥挤反转 | `duplicate_needs_mapping` | 映射至 `multi_coin_funding_crowding` |
| **FC_06** | 资金费率动量 | `context_feature_candidate` | 杠杆费率方向特征，非交易信号 |
| **FC_07** | 费率与价格背离度 | `context_feature_candidate` | 监测庄家锁仓/费率拉盘状态 |
| **FC_08** | 费率横向离散度 | `context_feature_candidate` | 监测全市场山寨币多空杠杆分化状态 |

### 6. 持仓量 (OI) 与杠杆状态家族 (OI_01 - OI_08)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **OI_01** | OI 独立变化率 | `duplicate_needs_mapping` | 映射至 `daily_oi_independent_change` |
| **OI_02** | OIVR 杠杆成交比 | `context_feature_candidate` | 杠杆堆积密度，仅作过滤器与环境标签 |
| **OI_03** | OI 去杠杆冲击 | `duplicate_needs_mapping` | 映射至 `oi_deleveraging_filter` |
| **OI_04** | 震荡区间 OI 极端变化 | `risk_filter_candidate` | 震荡中筹码异常堆积，拦截顺势开仓 |
| **OI_05** | OI 与价格背离 | `context_feature_candidate` | 监测资金流向（价涨量跌/价平量升） |
| **OI_06** | Funding + OI 联合状态 | `duplicate_needs_mapping` | 映射至 `funding_oi_time_corrected` |
| **OI_07** | 全网多空比拥挤度 | `context_feature_candidate` | 散户多空情绪分类特征 |
| **OI_08** | 去杠杆冷却过滤器 | `risk_filter_candidate` | 强力去杠杆踩踏后拦截开多 48 小时 |

### 7. 波动率状态家族 (VR_01 - VR_08)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **VR_01** | ATR 百分位数 | `context_feature_candidate` | 波动率大小分类（低波盘整 vs 高波剧震） |
| **VR_02** | 布林带带宽挤压度 | `context_feature_candidate` | 标示波动率收口状态 |
| **VR_03** | 历史波动率 HV 分位数 | `context_feature_candidate` | 收益率波动率状态分类 |
| **VR_04** | GARCH 波动率预测特征 | `blocked_from_combo` | 拟合极不平稳，无预测优势，禁用 |
| **VR_05** | 波动率 Regime 转换指数 | `context_feature_candidate` | 高低波状态机转移特征 |
| **VR_06** | ATR 动态风险跟踪带 | `context_feature_candidate` | 组合层总仓位波动控制参数，非开仓信号 |
| **VR_07** | Parkinson 极差波动率 | `context_feature_candidate` | 日内极差特征，适合 meta 标签 |
| **VR_08** | Garman-Klass 开闭盘波动率 | `context_feature_candidate` | 结合开闭盘与极差的精细波动标签 |

### 8. 时间段与季节性家族 (SS_01 - SS_08)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **SS_01** | UTC 00:00 收盘/开盘效应 | `context_feature_candidate` | 仅用作日线换线时的流动性冲击标签 |
| **SS_02** | 周末低流动性收缩 | `risk_filter_candidate` | **周末不交易过滤器**，拦截低频趋势突破 |
| **SS_03** | 费率结算点小时效应 | `blocked_from_combo` | 属于日内高频噪声，禁用 |
| **SS_04** | 星期效应（如周一/周五） | `context_feature_candidate` | 仅作静态状态标签 |
| **SS_05** | 美股开盘时段效应 (14:30 UTC) | `blocked_from_combo` | 15m 执行滑点过大，无法在本地复现，禁用 |
| **SS_06** | 亚盘开盘时段效应 | `blocked_from_combo` | 同样因为滑点和成交量碎片化禁用 |
| **SS_07** | 月度期权交割日效应 | `blocked_from_combo` | OKX 期权交割对山寨币永续影响无 365天 免费归档数据 |
| **SS_08** | 年度季节性效应 | `blocked_from_combo` | 样本不足，无长期免费数据支撑 |

### 9. 跨品种与套利家族 (CS_01 - CS_08)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **CS_01** | 交割与永续基差回复 | `duplicate_needs_mapping` | 映射至 `okx_futures_calendar_spread` |
| **CS_02** | 交割跨期价差动量 | `blocked_from_combo` | 跨期深度不足且换月摩擦巨大，禁用 |
| **CS_03** | 跨交易所现货/永续套利 | `blocked_from_combo` | 涉及多交易所，不满足本地 OKX 免费同市场约束 |
| **CS_04** | 多代币一篮子协整套利 | `blocked_from_combo` | 协整失效风险极大且换手磨损高，禁用 |
| **CS_05** | 期现基差动态网格 | `blocked_from_combo` | **`risk_blocked`** 网格变体，禁用 |
| **CS_06** | BTC Dominance 占有率 | `context_feature_candidate` | 极佳的环境标签（BTC dominance 上升利空山寨） |
| **CS_07** | 全市场山寨币相关性矩阵 | `context_feature_candidate` | 描述市场是否齐涨齐跌（系统性共振） |
| **CS_08** | 稳定币溢价指数 | `blocked_from_combo` | 无 365天 免费 OKX 本地历史归档数据 |

### 10. 网格/马丁/高风险 EA 家族 (EA_01 - EA_08)
- **全部状态**：**`blocked_from_combo` (风险受阻/强行禁用)**
- **名录**：
  - EA_01 (等距网格), EA_02 (等比马丁加仓), EA_03 (马丁/斐波那契仓位递增), EA_04 (浮亏锁仓对冲), EA_05 (双向不对称网格), EA_06 (多周期均值平摊加仓), EA_07 (爆仓边沿亏损补仓), EA_08 (无全局止损复利网格)
- **原因**：违反不得通过资金分配掩盖尾部爆仓风险的铁律，严禁以组合名义引入。

### 11. 机器学习与动态路由家族 (ML_01 - ML_08)
- **全部状态**：**`blocked_from_combo` (长期冻结)**
- **名录**：
  - ML_01 (随机森林多因子合并), ML_02 (XGBoost 收益率方向预测), ML_03 (LSTM 时序预测), ML_04 (K-Means 市场环境聚类), ML_05 (马尔可夫 Regime 转换状态机), ML_06 (强化学习动态路由), ML_07 (神经网络自适应权重调整), ML_08 (遗传算法多参数寻优)
- **原因**：在没有独立、已批准的物理弱特征前，严禁使用模型调参制造 alpha。ML 最多只能在第三阶段作为特征相关性聚类分析，不得产生交易信号。

### 12. 外部事件与舆情家族 (EV_01 - EV_08)
- **全部状态**：**`blocked_from_combo` (数据受阻/永久禁用)**
- **名录**：
  - EV_01 (推特关键字情绪), EV_02 (巨鲸链上转移监控), EV_03 (交易所净流入流出), EV_04 (大选/宏观利率事件), EV_05 (币安/OKX 上币新闻), EV_06 (GitHub 代码提交频次动量), EV_07 (Google Trends 搜索热度), EV_08 (DeFi TVL 锁仓价值变化)
- **原因**：缺乏 365天 以上免费、公开、同市场的历史结构化事件数据，发布对齐滑点无法回测。

### 13. 资金管理 Overlay 家族 (MM_01 - MM_07)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **MM_01** | ATR 波动率头寸调整 | `context_feature_candidate` | 组合层基础仓位计算特征 |
| **MM_02** | 凯利公式动态比例 | `blocked_from_combo` | 杠杆扩张过于激进，不符合极端行情风控要求 |
| **MM_03** | 波动率杠杆自动缩减 | `context_feature_candidate` | 杠杆调控特征，仅作 context |
| **MM_04** | 最大投资组合敞口限制 | `risk_filter_candidate` | 总仓位上限风险过滤器 |
| **MM_05** | 连亏后冷静期暂停 | `risk_filter_candidate` | 风控过滤器 |
| **MM_06** | 组合净值回撤硬止损 | `risk_filter_candidate` | 组合层全局保护阀，拦截所有特征信号 |
| **MM_07** | 最优 f 仓位增长模型 | `blocked_from_combo` | 对非平稳收益极度敏感，禁用 |

### 14. 组合层分配策略家族 (PM_01 - PM_08)
| 原型 ID | 原型名称 | 组合复用决策标签 | 映射研究 ID / 备注 |
| :--- | :--- | :--- | :--- |
| **PM_01** | 等风险贡献 (Risk Parity) | `context_feature_candidate` | 组合层只读权重分配算法 |
| **PM_02** | 马科维茨均值-方差优化 | `blocked_from_combo` | 在高度非平稳的 crypto 中极度易过拟合，禁用 |
| **PM_03** | 层次风险平价 (HRP) | `blocked_from_combo` | 时序相关性漂移大，不宜引入 |
| **PM_04** | 状态自适应动态权重分配 | `context_feature_candidate` | 根据大盘环境（CS_06）动态缩减山寨币特征权重 |
| **PM_05** | 币种相关性过滤限制 | `risk_filter_candidate` | 同板块代币高相关性时限制入场数量 |
| **PM_06** | 组合目标波动率跟踪 | `context_feature_candidate` | 波动率调配层 |
| **PM_07** | 净值导向型总杠杆缩减 | `risk_filter_candidate` | 风控机制 |
| **PM_08** | 横截面静态强弱度排名 | `context_feature_candidate` | 提供横截面打分排序框架 |

---

## 三、优先建议结构化接入组合特征池的前 30 个原型

根据**数据免费可得性（OHLCV + Funding + OI）**与**持有期约束（$\ge 3$天）**，筛选出以下 30 个最优先供后续 ClaudeCode 自动结构化导入 `strategy_feature_pool.py` 的特征候选：

### 1. 基础多空投票特征 (Directional Weak Signals) - 10 个
1. **TF_01**: Donchian 55突破 (4h周期突破)
2. **TF_03**: 均线 50/200 趋势交叉排列
3. **TF_08**: Ichimoku Cloud (云图多空差值)
4. **TF_10**: SuperTrend (动态多空转折趋势)
5. **BO_01**: 55日高低点通道收盘价突破
6. **BO_03**: ATR 波动率边界突破
7. **BO_04**: 突破时的放量乘数 (Volume-confirmed Breakout)
8. **MO_02**: 90日价格变化率动量评分 (ROC)
9. **MO_07**: 相对大盘 (BTC) 的超额收益率强度 (Alpha Rotation)
10. **MR_05**: 1d 周期 RSI 指标背离状态 (低频均值回复)

### 2. 市场状态环境标签 (Context Features) - 10 个
11. **TF_05**: ADX 指标（标示当前是否为单边趋势还是无方向震荡）
12. **TF_09**: 日线价格线性回归斜率 (Slope 标示市场冷热度)
13. **FC_06**: 全市场平均资金费率时序动量 (标示多空加杠杆速度)
14. **FC_07**: 费率与价格偏离度 (标示庄家锁仓与逼空指数)
15. **OI_02**: OIVR (日持仓量 / 24h交易量，标示杠杆与换手比值)
16. **OI_05**: OI 与价格背离指数 (标示是“增仓上涨”还是“空头不死”)
17. **VR_01**: ATR 14日百分位 (标示当前是否处于极度萎缩的低波状态)
18. **VR_02**: Bollinger Band 挤压宽度 (BB Width 标示蓄势突破期)
19. **CS_06**: BTC Dominance 指数 (BTC 占有率上升时降低山寨币做多投票)
20. **CS_07**: 全市场山寨币相关性离散度 (标示是否齐涨齐跌)

### 3. 拦截与风控过滤器 (Risk Filters) - 10 个
21. **MR_09**: 波动率通道极值边界 (拦截在超买超卖极端点的追高顺势)
22. **OI_04**: 震荡区间 OI 增仓速度 (防范主力诱多/诱空踩踏)
23. **OI_08**: 去杠杆踩踏冷却特征 (爆仓后强制禁止开多，起死回生冷却)
24. **SS_02**: 周末低流动性时段 (强行拦截所有新突破信号)
25. **PM_05**: 币种高度相关性过滤器 (同板块同向持仓不得超过 2 个)
26. **MM_04**: 组合总仓位比例限制 (任何时候多头或空头名义净敞口不得超标)
27. **MM_05**: 账户连续亏损冷静暂停特征 (冷却机制)
28. **MM_06**: 组合净值回撤硬止损线 (全局关闭)
29. **PM_07**: 组合回撤后阶梯型缩减总体交易杠杆上限
30. **FC_08**: 费率极值离散度 (拦截费率套利过度拥挤时的对手盘开仓)
