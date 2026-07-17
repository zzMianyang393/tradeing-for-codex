# 生产轨（Production Track）操作说明

更新日期：2026-07-17

## 你现在的目标

- **双轨**：多币研究轨 + **10U 高风险起步轨**
- **10U 优先**：用高风险策略滚资金，而不是低风险耗一年
- **不再把「前瞻空等」当作上模拟盘的前提**
- 回测可用 + 反过拟合检查通过 → **预备模拟盘（paper-prep）**
- 实盘必须另一步晋级，默认关闭

## 仓库怎么切（避免被旧代码淹死）

| 目录 / 入口 | 角色 |
|-------------|------|
| **`prod/`** | **唯一日常交易入口**（准入、注册表、10U paper 循环） |
| `ten_u_event_trend_*.py` | 10U 信号/回放引擎（被 prod 调用） |
| `runner.py` / `exchange.py` | OKX 模拟盘执行底座（下一步接自动下单） |
| 大量 `*_audit.py`、`docs/*_2026-07-*.md`、`reports/*` | **研究档案馆**，不阻塞 paper-prep |
| `data/` | 本地数据，**不进 GitHub**（见 `.gitignore`） |

旧研究代码先**不删**（避免丢证据），但 **Git 不再跟踪大数据/大批报告**，日常只碰 `prod/`。

## 10U 准入规则（paper-prep）

命令：

```bash
python -m prod.cli admit-ten-u --accept-concentration-risk
```

默认读：

1. `reports/ten_u_event_trend_informal_full_history_v2.json`（全量非正式回放）
2. 否则 `reports/ten_u_event_trend_screen_v2.json`

硬条件（可调，但改了要重准入）：

- 成交笔数 ≥ 6
- 结束权益 ≥ 10
- PF ≥ 1.0
- 最大回撤 ≤ 70%
- 账户未 ruin / 永久回撤停机

反过拟合：

- 单笔盈利占比过高 → **警告**
- 去掉最大赢家后权益过低 → 对 **高风险 10U** 可在 `--accept-concentration-risk` 下仍进 paper-prep
- **不**因此自动允许实盘

输出：

- `reports/prod/ten_u_admission.json`
- `reports/prod/paper_prep_registry.json`

## 跑预备模拟盘（本地 paper，不需要等前瞻）

```bash
# 推荐：刷新 OKX 公开 1H/资金费率 + 一轮本地 paper（带文件锁）
python -m prod.cli run-ten-u

# 有限次定时循环（Task Scheduler / cron 可每小时调一次，或本进程内循环）
python -m prod.cli watch-ten-u --iterations 1
# 进程内连跑 3 次、间隔 3600 秒：
# python -m prod.cli watch-ten-u --iterations 3 --interval 3600

# OKX 模拟盘执行演练（仅 ETH/BTC；拒绝 RAVE/LAB）
python -m prod.cli demo-drill --symbol ETH-USDT-SWAP
# 真下单+撤单（需 OKX_API_KEY/SECRET/PASSPHRASE 模拟盘密钥）：
# python -m prod.cli demo-drill --symbol ETH-USDT-SWAP --confirm-okx-smoke-order

# 仅刷新数据
python -m prod.cli refresh-ten-u

# 仅 paper 循环
python -m prod.cli paper-cycle

# 实盘/模拟盘可交易宇宙检查（RAVE/LAB demo 通常不可用）
python -m prod.cli universe-check

# 查看状态
python -m prod.cli status
```

锁文件：`reports/prod/prod_runtime.lock`（45 分钟过期可回收）。

本地瘦身（归档 candidate_pool / basis / calendar_spread）：

```bash
python -m prod.slim_local --archive-root ../tradering-archive/YYYY-MM-DD
```

行为：

- 检查注册表是否 `paper_prep`
- 用本地 1H 数据生成/管理 10U v2 仓位
- 状态：`reports/prod/ten_u_paper_state.json`
- 周期摘要：`reports/prod/ten_u_paper_cycle.json`
- **当前默认不下 OKX 真实/模拟单**（先把信号→仓位状态跑通）

## 下一阶段（尚未默认打开）

1. 接 `runner.py --okx-*`：注册表 paper_prep → OKX **模拟盘**自动下单  
2. 模拟盘跑满 N 笔 / M 天 → `graduated_live_capped`  
3. 小资金实盘（硬顶 10–50U）  

## 多币轨

暂不阻塞 10U。组合研究继续放在 audit 宇宙；要进 paper-prep 时同样走：

`回测报告 → prod.admission → registry → paper runtime`

## 明确不做

- 不要求 90 天前瞻空等才 paper
- 不在 paper 期间改 10U 冻结参数「救成绩」
- 不把 RAVE 神单污染回测当成实盘许可证
