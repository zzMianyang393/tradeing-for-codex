# 服务器部署：瘦身后从 Git 拉取并跑模拟盘/本地 paper

适用场景：**交易不在本机跑**，而在远端服务器。  
Git 只含代码；**不含** `data/`、`reports/` 大体量文件。

## 架构分工

| 机器 | 职责 |
|------|------|
| 开发机 | 改代码、commit、`git push`；可选本地回测 |
| **服务器** | `git pull` → bootstrap 数据 → 定时 `watch-ten-u` / `demo-drill` |
| OKX 模拟盘 | 仅 **ETH/BTC** 等 demo 支持的合约做执行演练；**RAVE/LAB 用本地 paper + 实盘行情** |

```text
GitHub (slim code)
    │ git pull
    ▼
Server
  ├── prod/  ten_u_*  exchange/runner
  ├── data/event_trend_v1/     ← bootstrap 从 OKX 公开接口下载
  └── reports/prod/            ← 运行时状态（勿提交）
```

## 1. 开发机：推送瘦身代码

```bash
# 已在本地做过 untrack data/reports 的前提下
git push origin main
```

确认远程没有强制依赖本地 `data/`。

## 2. 服务器：首次拉取

```bash
# 示例
git clone https://github.com/zzMianyang393/tradeing-for-codex.git tradering
cd tradering
python --version   # 建议 >= 3.10
```

无第三方硬依赖时，生产轨以标准库 + 现有模块为主。若你之后加了依赖，再补 `requirements-prod.txt`。

## 3. 服务器：冷启动（下载 10U 数据 + 注册 paper-prep）

```bash
python -m prod.bootstrap_server
```

会做：

1. 下载 RAVE/LAB/ETH **1H K 线** → `data/event_trend_v1/`
2. 下载对应 **funding** CSV  
3. 写 `hourly_dataset_manifest_v1.json`  
4. 若无注册表，**seed** `reports/prod/paper_prep_registry.json`（高风险 10U，live 仍关闭）

报告：`reports/prod/server_bootstrap.json`

> 首次下载可能需数分钟（OKX 分页）。可重跑；增量之后用 `run-ten-u` / `watch-ten-u`。

## 4. 服务器：日常命令

```bash
# 可交易宇宙（live 有 / demo 政策）
python -m prod.cli universe-check

# 刷新 + 本地 paper 一轮（带锁）
python -m prod.cli run-ten-u

# 每小时一次（cron / systemd timer 推荐）
python -m prod.cli watch-ten-u --iterations 1

# OKX 模拟盘执行演练（仅 ETH；需模拟盘 API Key）
export OKX_API_KEY=...
export OKX_API_SECRET=...
export OKX_API_PASSPHRASE=...
python -m prod.cli demo-drill --symbol ETH-USDT-SWAP
# 确认后 smoke：
python -m prod.cli demo-drill --symbol ETH-USDT-SWAP --confirm-okx-smoke-order
```

## 5. 定时任务示例（Linux cron）

```cron
# 每小时第 5 分钟（等 K 线收盘缓冲）
5 * * * * cd /path/to/tradering && /usr/bin/python3 -m prod.cli watch-ten-u --iterations 1 >> /var/log/tradering-watch.log 2>&1
```

锁文件：`reports/prod/prod_runtime.lock`（防重叠；约 45 分钟过期可回收）。

## 6. 密钥与安全

- 模拟盘 Key **只放服务器环境变量或权限收紧的 env 文件**，不要进 Git  
- `sandbox=True`（`demo-drill` / runner OKX 路径默认模拟）  
- **不要**把 live key 配进未审查的自动任务  

## 7. 更新流程

开发机改完 → push → 服务器：

```bash
cd /path/to/tradering
git pull
# 一般不必重新 bootstrap；数据用 refresh 即可
python -m prod.cli run-ten-u
```

仅当 manifest/数据目录损坏时再：

```bash
python -m prod.bootstrap_server --force-registry   # 仅必要时
```

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| `blocked_not_in_paper_prep_registry` | 跑 `bootstrap_server` 或 `admit-ten-u`（若你拷了回测报告） |
| `dataset fingerprint drift` | `refresh-ten-u` 或重新 bootstrap |
| demo-drill 缺凭证 | 配置 `OKX_*` 模拟盘密钥 |
| demo-drill RAVE/LAB | **设计拒绝**；10U 信号用 local paper |
| Git 很大 / 推不动 | 确认未再次 `git add data reports` |

## 9. 与本机的关系

- **本机**：研发、可选回测、push  
- **服务器**：拉代码、bootstrap、跑 paper + demo ETH  
- **状态文件**（`reports/prod/*.json`）留在服务器，不要当 Git 同步手段  
