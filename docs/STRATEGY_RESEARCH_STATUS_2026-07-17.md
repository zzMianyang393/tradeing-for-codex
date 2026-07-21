# 策略研究总览（2026-07-17）

## 一句话

在 **BTC/ETH、10U、含成本、禁止挑币** 约束下，批量否定了多数家族；发现并撤销了 **数据假 edge**；最终 **仅 1 个规则** 通过严格 multiwindow + 分年闸门，进入 **本地 paper_prep**：**1h 高波动 donchian short**。  
**模拟盘/实盘：未开。**

---

## 硬约束（全程）

| 项 | 规则 |
|----|------|
| 标的 | 默认 BTC + ETH only |
| 资金 | 回测/paper 默认 10U；敏感性最高 500U |
| 晋级 | 回测 → 本地 paper →（服务器）demo 见效 → 实盘 |
| 本机 | 不配交易 API、不下 demo/live 单 |

---

## 研究流水线做了什么

| 阶段 | 内容 | 结果 |
|------|------|------|
| 工程轨 | prod 注册表、paper、刷新、handoff、policy | 就绪 |
| v1–v4 | 15m / 日线稀疏族、dual、weekly 等 | 几乎无 durable edge |
| v5 | 原生 1h + funding | 一度准入 md_mom short → **后撤销** |
| 数据事故 | ETH 1h 时间戳损坏导致假对齐 | **假 edge 曝光** |
| Primary health | 15m donchian long multiwindow | **−67%，suspend** |
| v6 | 1h 未测族 + 原生 4h | weekly/dual 等仅 watchlist |
| v7 | 波动 regime / 假突破 / 时段 / 相对强弱 | **高波动 short 通过** |

---

## 关键结果（registry）

| strategy_id | 状态 | 含义 |
|-------------|------|------|
| **`prod_majors_h1_high_vol_donchian_short_v1`** | **paper_prep** | 当前唯一 majors 活跃 paper alpha |
| `prod_majors_donchian_atr_long_v1` | suspended | 15m long 全样本约 −67% |
| `prod_majors_h1_md_mom_short_v1` | rejected | 损坏数据假 edge |
| ten_u RAVE/LAB | paper_prep | 仅本地实验，**不可** demo/live 晋级 |

### 存活策略（回测摘要）

| 项 | 值 |
|----|-----|
| 规则 | 1h：ATR% 分位 ≥ 0.70 **且** donchian short |
| 全样本 | **+68.3%**，PF **1.21**，233 笔，DD ~33% |
| Multiwindow | formation **3/3**，OOS **3/3** |
| 分年 | 2024 +16% / 2025 +9% / 2026 +33%（全正） |
| 10/100/500 | 收益同构（无 min-notional 扭曲） |
| Paper | hourly 已通；cycles=2；尚无成交；**不下单** |
| Demo/live | **关闭** |

定时 paper：`scripts/prod_majors_h1_high_vol_hourly.ps1`

---

## 明确否定 / 仅观察

| 结论 | 例子 |
|------|------|
| 失败 | 多数 15m 趋势 long、BB/session 高频、裸 md_mom 1h（干净数据） |
| 假阳性已撤销 | h1_md_mom_short（ETH 时间戳损坏） |
| 近期行情伪 edge | h4_weekly_mom_short、h4_high_vol_donchian_short（formation 弱） |
| 样本过薄 | dual failed-breakout、部分 sparse dual |

---

## 运维看板说明

`ops-summary` 默认盯 **15m donchian** → 现为 **suspended** → overall **degraded**。  
这不表示系统崩溃，表示 **默认 majors 主袖套已停**；活跃 paper 在 **独立 1h state**，需用对应 strategy-id 命令跑。

---

## 还没到哪里

1. Paper 成交历史不足（需约 20 笔 / 30 cycle 才谈 local graduation）  
2. 服务器 demo / 实盘：未配置、未授权  
3. 第二个 durable edge：尚未找到  
4. 已准入规则：**禁止调参**  

---

## 关键判断

- **研究质量：** 闸门变严（数据清洗 + multiwindow + 分年），避免再次假准入。  
- **可交易准备度：** 工程可 paper；**alpha 仅 1 条 1h short 规则**在本地观察中。  
- **对用户目标（能上盘）：** 仍早；下一步是 **挂定时 paper 攒证据**，不是开模拟盘。

## 组合对照（同日追加）

| 协议 | 是否超过主策略 |
|------|----------------|
| 等权资金拆分 | **否**（全面稀释，约 −23～−41pp） |
| 1h 优先级单仓（高波动 short + 假突破/假跌破） | **是**（全样本最高约 +95.6% vs +68.3%；multiwindow OOS 也更好） |

**操作：** paper 仍只跑主策略；组合需单独工程化后再准入。详见 docs/research_majors_combo_2026-07-17.md。

