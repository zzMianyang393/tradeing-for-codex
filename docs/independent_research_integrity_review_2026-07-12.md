# 独立研究完整性审查报告

**审查日期**：2026-07-12  
**审查范围**：研究方向 A（期现微结构）、B（Funding+OI 联合信号）、D（数据扩展）、E（多币种 Funding 拥挤）  
**审查原则**：只读；不修改任何文件；不提出新策略；不做参数搜索  
**审查标准**：前视偏差、成本核算、市场同源性、样本分割、少数事件驱动

---

## 方向 A：期现微结构（basis_microstructure_audit.py）

### 审查结论：可接受，结论维持淘汰

### 数据同源性
- 数据源：`data/basis/BTC-USDT_spot_1m.csv` + `data/basis/BTC-USDT_swap_1m.csv`，及 ETH 同格式文件
- OKX 同市场数据（现货+永续），符合规则，无跨交易所污染

### 前视偏差检查
- 信号构建（L132-175）：在每个 bar `i` 处，仅使用 `bars[i-lookback:i]` 的历史数据计算 rolling stdev，当前 bar `i` 的基差突变信号使用当前 bar 完成后的 `basis_change_bps`
- 前向收益从 `bars[i+horizon]` 取，不混入当前 bar 收盘价
- 无明显前视偏差

### 入场语义注意事项
- 脚本为纯统计研究（`research audit, NOT a strategy`），计算基差突变后的前向价格路径，不涉及下单
- 前向收益使用 `spot_close`/`swap_close`，若要转化为策略应使用下一根 bar 的 `open`——当前是一个轻微的统计乐观偏差，但对于淘汰结论无实质影响

### 成本核算
- 报告数据（`reports/basis_microstructure_audit.json`）：
  - BTC：1bar 均值 +0.0066%，4bar +0.0003%，16bar -0.0191%
  - ETH：1bar 均值 +0.0024%，4bar -0.0395%，16bar -0.0023%
- OKX 双边成本 0.16%，所有时间窗口的原始前向收益均远低于 0.16%，即便不显式扣除成本，结论仍为淘汰

### 其他观察
- 波动率聚集（Vol Clustering）发现 basis vol 与未来价格 vol 相关性 BTC=0.50，ETH=0.38——这是描述性发现，不是可交易信号

### 最终判定
**可接受。淘汰结论维持，无需重新运行。**

---

## 方向 B：Funding + OI 联合信号（funding_oi_joint_audit.py）

### 审查结论：存在重大前视偏差，正收益结论作废

**WARNING：以下发现的偏差直接影响报告数字的可信度，正期望数字不得引用。**

### 数据同源性
- Funding 数据：OKX 永续 funding rate，来源 `{symbol}_funding.csv`，符合规则
- OI 数据：`{symbol}_open_interest_1d.csv`，OKX 同源，符合规则
- OHLCV：OKX 15m K线，符合规则
- 无跨交易所污染

### 前视偏差检查（关键问题）

**问题 1：OI 可用时间未处理**

`load_oi_daily`（L44-58）将日线 OI 的时间戳直接映射为 `"YYYY-MM-DD"` 字符串：

```python
day = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
oi[day] = float(row["open_interest_usd"])
```

`compute_daily_joint_signals`（L82-128）随后使用：
```python
today = reference_days[i]   # 例如 "2024-11-06"
oi_change = all_oi[symbol][today] - all_oi[symbol][yesterday]
```

**核心问题**：若 OI 数据的时间戳是 `2024-11-06 00:00 UTC`，则被视为 `"2024-11-06"` 当天已知，但 OI 数据通常需到 16:00 UTC 收盘后才实际可用。代码中完全没有 OI 可用时间的延迟处理。

任务说明书声称"OI 实际可用时间按 16:00 UTC，信号后 16:15 UTC 才能入场"——代码中未实现此约束。

**问题 2：入场时间早于 OI 实际可用时间**

`compute_forward_returns`（L167-183）：
```python
event_dt = datetime.strptime(event_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
event_ts = int(event_dt.timestamp() * 1000)  # 当天 00:00 UTC
entry_idx = next(ts >= event_ts ...)          # 找到当天第一根 15m bar
```

信号使用了"当天 OI"，但入场却是"当天 00:00 UTC 开盘"——在 OI 实际可用之前已经入场，构成前视偏差。

**问题 3：已声称修复，但代码中未体现**

任务说明书称"Claude 已声称修复"——经代码审查，`funding_oi_joint_audit.py` 和 `funding_oi_joint_full_audit.py` 中均未实现 OI 延迟约束。

**问题 4：无形成期/样本外分割**

代码以全部 365 天为单一窗口，无任何分割。任务说明书称"有形成期/样本外分割"——代码中未实现。

### 少数事件驱动风险

`reports/funding_oi_joint_audit.json` 中：
- fwd_96bar（24小时）净均值 +3.93%，来自 29 个事件
- 事件 `2024-11-06`：fwd_96bar mean +12.99%（Trump 当选 BTC 暴涨日，属于一次性宏观冲击）
- 2024-11 月共有 5 个事件（占 17.2%），恰逢历史上 BTC 涨幅最大的月份之一
- **正期望很可能由单一宏观事件主导，而非信号本身有效**

### 成本核算
- `COST_ROUND_TRIP = 0.0016`（双边 0.16%），计算方式正确
- 成本本身无误，但建立在有偏差的前向收益基础上，数字不可信

### 最终判定
**结论作废。存在以下问题：**
1. OI 前视偏差（当天 OI 在 00:00 UTC 被当作已知）
2. 入场时间早于 OI 实际可用时间（至少早 16 小时）
3. 无形成期/样本外分割
4. 正收益高度集中于 2024-11 Trump 当选宏观事件
5. "已声称修复"的 OI 延迟约束在代码中不存在

**`reports/funding_oi_joint_audit.json` 中的 fwd_4bar/fwd_16bar/fwd_96bar 正期望数字不得作为有效证据。**

若需恢复评估，必须同时满足：
1. OI 信号延迟：仅使用对应日期 16:00 UTC 之后可用的 OI，即用前一天的 OI 和当天结算后的 OI 做 change 计算
2. 入场时间：16:15 UTC 之后的第一根 15m bar 的 open
3. 形成期/样本外分割（前 180 天形成期，后 180 天样本外）
4. 剔除已知宏观事件日后测试结论稳定性

---

## 方向 D：数据扩展

### 审查结论：基本可接受，有三项使用限制

### 数据文件确认
通过 `data/` 目录审查，已确认：

| 数据类型 | 实际覆盖币种数 | 备注 |
|---------|------------|------|
| `*_funding.csv`（有 meta） | 约 22 币 | BNB/SEI/SOL/XRP 无 meta 或体积极小 |
| `*_open_interest_1d.csv` | 25 币（无 IMX） | IMX 无日线 OI 文件 |
| `*_15m.csv` | 29 币 | 全覆盖 |

### 数据来源确认
- 所有文件均位于 `data/` 目录，文件名前缀均为 OKX 标准命名（`XXX-USDT-SWAP_`）
- 无 Binance 数据混入 15m 或 funding 分析
- 符合"OKX 同源"要求

### 使用限制 1：部分币种 Funding 覆盖不足
- `BNB-USDT-SWAP_funding.csv`：无 `.meta.json`，覆盖状态未知（文件 22KB，约 280 条，仅 94 天）
- `SEI-USDT-SWAP_funding.csv`：仅 7.7KB，约 96 条，不足 32 天
- `SOL-USDT-SWAP_funding.csv`：23KB，约 280 条，约 94 天
- `XRP-USDT-SWAP_funding.csv`：23KB，约 280 条，约 94 天
- **以上四币不得用于年度（365 天）funding 研究**

### 使用限制 2：IMX 无日线 OI
- `data/` 目录中无 `IMX-USDT-SWAP_open_interest_1d.csv`
- 任何需要 OI 的分析（方向 B、D）均不得包含 IMX

### 使用限制 3：日线 OI 的 Intraday 共享问题
- 日线 OI 每天只有一个值，当用于 15m 研究时，同一天内每 15 分钟的入场均共享该值
- 约束：不得将日线 OI 降频使用为 15m 信号；日线 OI 只能产生日频信号
- 现有代码通过"以日为单位产生信号"部分规避，但任何绕过该约束的扩展必须重新审查

### 最终判定
**基本可接受。须遵守三项使用限制，违反者的研究结论无效。**

---

## 方向 E：多币种 Funding 拥挤（multi_coin_funding_crowding_audit.py）

### 审查结论：可接受，结论维持淘汰

### 数据同源性
- 数据：OKX 永续 funding，25 币，来源 `{symbol}_funding.csv`
- OHLCV：OKX 15m
- 无跨交易所污染

### 前视偏差检查
**信号构建（L72-109）**：
- 以 BTC 的 funding settlement timestamps 为参考时间轴
- 对每个 settlement ts，查找各币种在该时间点的 funding rate
- funding settlement 时间戳是结算完成时间，信号使用当前已结算的 rate，不依赖未来数据
- **无前视偏差**

### 入场语义（本次审查中最严格）
```python
for idx, ts in enumerate(sorted_ts):
    if ts > event_ts:   # 严格大于，找下一根 15m bar
        entry_idx = idx
        break
entry_price = lookup[entry_ts]["open"]   # 使用下一根 bar 开盘价
```
- 使用严格大于（`>`），确保入场在 funding settlement 之后
- 使用下一根 bar 的 open 作为入场价格
- **入场语义正确，是四个方向中最严格的**

### 成本核算
- `COST_ROUND_TRIP = 0.0016`，双边 0.16%，与项目设置一致，计算正确

### 报告数字评估
`reports/multi_coin_funding_crowding_audit.json`：
- 46 个事件
- fwd_1bar avg_net -0.32%
- fwd_4bar avg_net -0.37%
- fwd_16bar avg_net -0.44%
- **全部窗口为负，结论清晰，不存在"做反方向"能正期望的情况**

### 最终判定
**可接受。实现最为严格。淘汰结论维持，无需重新运行。**

---

## 综合总结

| 方向 | 审查结论 | 关键发现 | 操作要求 |
|------|---------|---------|---------|
| A 期现微结构 | 可接受 | 无前视偏差，统计研究合规，信号远低于成本 | 淘汰结论维持 |
| B Funding+OI 联合 | 结论作废 | OI 前视偏差未修复；入场时间早于 OI 可用时间；正收益集中于 2024-11 单一宏观事件；无样本外分割 | 正期望数字不得引用；需按规范重新实现后重新运行 |
| D 数据扩展 | 基本可接受 | BNB/SEI/SOL/XRP funding 覆盖不足；IMX 无日线 OI；日线 OI 禁止降频 | 注明使用限制；违反限制的研究无效 |
| E 多币种拥挤 | 可接受 | 入场语义最严格；全部窗口亏损；结论清晰 | 淘汰结论维持 |

### 核心警告

方向 B 的 `funding_oi_joint_audit.py` 中，OI 前视偏差约束未实现。任务说明书中声称的修复（"OI 实际可用时间按 16:00 UTC"）在代码中不存在。`reports/funding_oi_joint_audit.json` 中的所有正期望数字（fwd_4bar avg_net +0.29%，fwd_16bar +1.11%，fwd_96bar +3.93%）均不得用于任何策略决策。

当前经过有效独立审查确认的结论：

- A 淘汰（有效）
- B 未通过审查，结论待定
- E 淘汰（有效）
- 方向 D 数据有效，可用于满足使用限制的研究

---

*本文件由独立审查生成，审查期间未修改任何 Python、配置、数据、报告或策略文件。*
*仅新建：docs/independent_research_integrity_review_2026-07-12.md*
