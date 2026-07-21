# 组合 vs 单策略对照（2026-07-17）

**问题：** 把策略组合起来会不会超过现在的 `h1_high_vol_donchian_short`？  
**命令：** `python -m prod.cli research-majors-combo`  
**证据：**  
- `reports/prod/research_majors_combo_v1.json`  
- `reports/prod/research_majors_combo_oos_v1.json`

## 协议（冻结，不调参）

| 协议 | 含义 |
|------|------|
| **independent_equal_weight** | 各腿独立 10U 全样本，组合收益 = 等权平均（资金拆分模型） |
| **priority_single_slot** | 同周期 1h；最多 1 仓；按优先级第一条有信号的腿入场 |

基准主策略全样本：**+68.3%**，PF 1.21，233 笔，DD 32.9%。

## 结果摘要

### A. 独立等权（资金拆分）

| 组合 | 组合收益 | vs 主策略 |
|------|---------:|----------|
| high-vol + failed breakout short | +36.6% | **差 −31.7pp** |
| high-vol + failed breakdown long | +38.2% | **差 −30.1pp** |
| high-vol + 两腿 failed | +27.1% | **差 −41.2pp** |
| high-vol + h4 weekly | +45.3% | **差 −23.0pp** |
| high-vol + h4 high-vol | +39.5% | **差 −28.8pp** |
| high-vol + m15 failed breakout | +37.5% | **差 −30.9pp** |

**结论：** 等权把弱腿/中等腿混进去会 **明显稀释** 主策略。  
→ **不要用「各策略平分资金」替代主策略。**

### B. 优先级单仓（共享账户）

| 优先级顺序 | 收益 | vs 主策略 | 笔数 | DD | 入场构成 |
|------------|-----:|----------:|-----:|---:|----------|
| high-vol → failed BO short | **+77.9%** | **+9.5pp** | 248 | 30.7% | 230 + 18 |
| high-vol → failed BD long | **+85.1%** | **+16.8pp** | 242 | 29.4% | 233 + 9 |
| high-vol → BO short → BD long | **+95.6%** | **+27.2pp** | 257 | 27.1% | 230 + 18 + 9 |
| failed BO → high-vol（反序） | +77.9% | +9.5pp | 248 | 30.7% | 同 18+230 |

主策略仍贡献 **绝大多数** 成交；辅腿只在主策略无信号时「填空」。

### C. Multiwindow（三腿优先级）

| Form 比例 | 主策略 form / OOS | 组合 form / OOS | 组合 OOS 更好？ |
|----------:|------------------:|---------------:|:--------------:|
| 0.50 | +28.8% / +30.7% | **+34.8% / +45.1%** | 是 |
| 0.60 | +15.9% / +45.2% | **+25.6% / +55.7%** | 是 |
| 0.70 | +7.8% / +56.1% | **+24.6% / +56.9%** | 是 |

**三腿优先级在 formation 与 OOS 上均不低于主策略，多数窗明显更好。**

## 决策

| 问题 | 结论 |
|------|------|
| 组合会不会超过现在？ | **可以（在优先级单仓协议下）** |
| 等权资金拆分？ | **不会，反而更差** |
| 现在是否改 paper 主链为组合？ | **暂不**（辅腿单独未过准入；paper runtime 仍是单 family） |
| 是否值得继续？ | **是** — 作为下一工程：实现 priority multi-signal paper，再单独准入组合 sleeve |

### 操作决定

1. **本地 paper 继续只跑** `prod_majors_h1_high_vol_donchian_short_v1`。  
2. **不**把 failed-break 腿单独准入。  
3. 组合结论记为研究成功方向：`priority_single_slot(high_vol, failed_BO, failed_BD)`。  
4. demo/live 仍关闭。

## 解释（直观）

- 等权 = 强迫一半资金去跑弱策略 → 拖累。  
- 优先级 = 仍以高波动做空为主，空闲时用假突破/假跌破补几笔 → 全样本与 OOS 略增厚，回撤略降。
