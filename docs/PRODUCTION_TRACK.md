# 生产轨（Production Track）操作说明

更新日期：2026-07-17（硬约束修订）

## 运行边界（2026-07-17 起强制）

| 环境 | 做什么 | 不做什么 |
|------|--------|----------|
| **本机 / 当前工作区** | 策略研究、回测、本地 paper 指纹、就绪包、文档与可部署代码 | **不**跑 OKX 模拟盘/实盘；**不**配置/使用交易 API Key |
| **服务器** | 定时 paper、（后期）模拟盘/实盘执行 | 密钥仅由**服务器 agent** 注入环境，不进 Git、不在本机演练 |

本机交付物给服务器：`git push` → 服务器 `git pull` → agent 配置 `OKX_*` → 再开 demo/live。  
详见 **[SERVER_DEPLOY.md](./SERVER_DEPLOY.md)**。

```bash
# 服务器侧示例（本机不跑密钥相关）
python -m prod.cli bootstrap-server --mode majors   # 默认 BTC/ETH
python -m prod.cli majors-hourly --commit-refresh
python -m prod.cli server-handoff                   # agent 契约 JSON
# 模拟盘/实盘：仅服务器 agent 配好密钥后启用，本机不做
# 说明：docs/SERVER_HANDOFF.md
```

## 硬约束（2026-07-17，决策层）

| 约束 | 规则 |
|------|------|
| 晋级 | **回测/本地 paper →（服务器）模拟盘见效 →（服务器）实盘**；禁止跳级 |
| 模拟盘/实盘 | **都放最后**；且**只在服务器**运行；本机默认只跑本地 paper / 研究 |
| 密钥 | **本机不配置交易 API**；模拟盘与实盘密钥仅服务器 agent 管理 |
| 标的 | **默认 BTC + ETH**；禁止多币回测后挑赢家币；RAVE/LAB 不可作模拟/实盘晋级标的 |
| 资金 | 回测/paper **默认 10U**；仅当最小名义等导致 10U 失真时对照 **100–500U**，**最高 500U**；升高本金必须保留 10U 基线说明 |

**机器可读实现：** `prod/policy.py`（`operator_policy_snapshot` / `validate_start_equity` / `validate_production_bound_universe`）。  
`python -m prod.cli status` 会输出 `operator_policy` 与双袖套状态。  

| 袖套 | 命令 | 标的 | 晋级角色 |
|------|------|------|----------|
| **majors production-bound** | `majors-replay` / `admit-majors` / `paper-cycle-majors` / `run-majors` / `watch-majors` / `majors-capital-sensitivity` | BTC+ETH | 未来 demo/live 唯一候选宇宙 |
| 遗留 10U | `paper-cycle` / `run-ten-u` | RAVE/LAB/ETH | **local_experiment only**，不可 demo/live |

资本敏感性：`python -m prod.cli majors-capital-sensitivity`（默认 10/100/500，>500 拒绝；必须保留 10U 基线）。  
定时本地 paper：`python -m prod.cli watch-majors --iterations 1`（锁 + 本地 preflight，**无交易所**）。  
运维摘要：`python -m prod.cli ops-summary` 或 `status`（含 `ops_dashboard` / 各袖套 `ops_summary`）。  
Halt 恢复（仅本地账本）：`python -m prod.cli clear-halt --mode clear_halt_only|flat_and_clear|hard_reset_paper`  
- `hard_reset_paper` 需 `--confirm-hard-reset`；**永不**打开 live/demo。  
**本地就绪包：** `python -m prod.cli majors-readiness`  
- 主规则 10U 指纹 + 10/100/500 敏感性 + 保守规则旁路对照 + ops/graduation + `admission_notes`  
- 保守规则 **不是** 默认 paper runtime；仅对照  
- `ready_for_demo` / `ready_for_live` 恒为 false  
**运维挂接：** `python -m prod.cli ops-summary` 自动附带已有就绪包指针；`--rebuild-readiness` 可重算。  
**15m 增量刷新（BTC/ETH 公共行情）：**  
`python -m prod.cli majors-refresh-15m`（默认 dry-run）  
`python -m prod.cli majors-refresh-15m --commit`（写本地 CSV）  
`python -m prod.cli run-majors --refresh-data [--commit-refresh]`  

**1h 增量刷新（OKX bar=`1H`，canonical `BTC_1h.csv`/`ETH_1h.csv`）：**  
`python -m prod.cli majors-refresh-1h`（默认 dry-run）  
`python -m prod.cli majors-refresh-1h --commit`  
`python -m prod.cli majors-preflight --strategy-id prod_majors_h1_md_mom_short_v1`  

**定时一键（刷新→本地 paper）：**  
`python -m prod.cli majors-hourly --commit-refresh`  
`python -m prod.cli watch-majors --iterations 1 --refresh-data --commit-refresh`  
Windows 示例：`scripts/prod_majors_hourly.ps1`（Task Scheduler 可挂）  

**1h research 袖套 paper（独立 state/lock，不碰 15m donchian 账本）：**  
```bash
python -m prod.cli majors-hourly \
  --strategy-id prod_majors_h1_md_mom_short_v1 \
  --state reports/prod/h1_md_mom_short_paper_state.json \
  --cycle-out reports/prod/h1_md_mom_short_paper_cycle.json \
  --lock reports/prod/h1_md_mom_short_runtime.lock \
  --out reports/prod/h1_md_mom_short_hourly_job.json \
  --commit-refresh
```
Windows：`scripts/prod_majors_h1_hourly.ps1`。**仅本地 paper**；demo/live 仍只在服务器。  

**阶段 3 清单（交付服务器用，本机不跑 demo）：**  
`python -m prod.cli demo-checklist`  
- 通过 = 代码/宇宙/本地 paper 侧工程就绪，供**服务器 agent** 接密钥  
- **永不**在本机启用 auto-trading；清单通过 ≠ 本机下单  

默认本机 **不下交易所单、不配交易 API**。

完整阶段表见 [`SYSTEM_ROADMAP_AND_SLIM_PLAN.md`](./SYSTEM_ROADMAP_AND_SLIM_PLAN.md) §0A / §4。

## 你现在的目标

- **本机主轨**：本地 paper + 可复现回测（**BTC/ETH，默认 10U**）+ 可部署代码  
- **模拟盘/实盘**：仅服务器；密钥由服务器 agent 配置  
- 回测可用 + 反过拟合检查通过 → **本地 paper-prep**（不是本机模拟盘）

### 2026-07-17 状态快照（决策层）

| strategy_id | registry | 说明 |
|-------------|----------|------|
| **`prod_majors_h1_high_vol_donchian_short_v1`** | **paper_prep** | v7：1h 高波动 donchian short；multiwindow+分年通过 |
| `prod_majors_donchian_atr_long_v1` | **suspended** | 15m health：全样本约 −67%、peak DD halt |
| `prod_majors_h1_md_mom_short_v1` | **rejected** | 数据完整性假 edge |
| ten_u RAVE/LAB | paper_prep (local_experiment) | **不可** demo/live 晋级 |

当前 majors **活跃本地 paper**：仅 `h1_high_vol_donchian_short`（独立 state/lock）。  
定时：`scripts/prod_majors_h1_high_vol_hourly.ps1` 或 `majors-hourly --strategy-id prod_majors_h1_high_vol_donchian_short_v1 ...`。  
资本敏感性：`majors-capital-sensitivity --strategy-id prod_majors_h1_high_vol_donchian_short_v1`（10/100/500 收益同构；基线仍 10U）。  
运维记录：`docs/h1_high_vol_donchian_short_ops_2026-07-17.md`。

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

## 下一阶段（按硬约束排序）

**现在（阶段 1–2）**

1. 稳定本地 paper（锁、刷新、halt、状态）  
2. **BTC/ETH production-bound 袖套（已代码化）**：`prod/majors_*.py`  
   - `python -m prod.cli majors-replay --start-equity 10`  
   - `python -m prod.cli admit-majors`  
   - `python -m prod.cli paper-cycle-majors`  
3. **本地毕业闸门（已代码化）**：`prod/graduation.py`  
   - 成交 ≥20 **或** 完成 cycle ≥30，且未 halt、无交易所下单、`live_allowed` 恒 false  
   - 决策：`graduated_local` | `not_yet` | `blocked`  
   - `graduated_local` **不等于** 模拟盘/实盘；RAVE/LAB 仅 local_experiment，不可 demo/live  
   - 见：`python -m prod.cli status` → `local_graduation`；`paper-cycle` 报告同字段  

**后期才打开（阶段 3–4，仅服务器）**

1. 服务器 agent 注入模拟盘密钥 → 仅 BTC/ETH → 模拟盘策略/执行  
2. 模拟盘见效 → 服务器再注入实盘密钥（硬顶）  
3. **本机不参与** demo/live 运行与密钥配置  

`demo-drill` / `runner` 等为服务器侧工具；本机仓库只维护代码与本地 paper 证据。  
本地 `graduated_local` **不**自动打开 demo/live。

## 多币 / 冷门币

- 研究档案馆可保留多币 audit，**不**作为晋级主链。  
- 要进 paper-prep / 未来模拟盘：宇宙必须是 **BTC+ETH** 或**预注册固定全集（不挑币）**。  
- 路径：`回测报告 → prod.admission → registry → local paper` →（后期）demo → live  

## 明确不做

- 不要求 90 天前瞻空等才本地 paper  
- 不在 paper 期间改冻结参数「救成绩」  
- 不把 RAVE/LAB 或其它模拟盘不可交易标的当成模拟/实盘许可证  
- 不在模拟盘见效前开实盘  
- 不在本机配置/演练交易 API Key（模拟盘与实盘均在服务器由 agent 配置）  
- 不用 >500U 回测粉饰 10U 策略  
- 不从多币结果里 cherry-pick 标的再声称可部署  
