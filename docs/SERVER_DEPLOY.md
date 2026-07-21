# 服务器部署：majors 优先（BTC/ETH 本地 paper）

适用场景：**交易与密钥不在开发机**，而在远端服务器；密钥由**服务器 agent** 注入。  
Git 只含代码；**不含** `data/`、`reports/` 大体量文件、**不含** API Key。

更完整的 agent 契约见 **[SERVER_HANDOFF.md](./SERVER_HANDOFF.md)**。

## 架构分工

| 机器 | 职责 |
|------|------|
| 开发机 | 改代码、回测、本地 paper 证据、`git push`；**不配交易密钥、不跑 demo/live** |
| **服务器** | `git pull` → `bootstrap-server --mode majors` → 定时 `majors-hourly`；**agent 配置 OKX_***（后期） |
| OKX 模拟盘/实盘 | **仅服务器**；合约默认 **BTC/ETH**；RAVE/LAB 不可作晋级标的 |

```text
GitHub (slim code)
    │ git pull
    ▼
Server
  ├── prod/  majors_*  (primary)
  ├── data/BTC_15m.csv  ETH_15m.csv
  └── reports/prod/     ← 运行时状态（勿提交）
```

## 1. 开发机：推送代码

```bash
git push origin main
```

确认远程不依赖本机 `data/` / 密钥。

## 2. 服务器：首次拉取

```bash
git clone <your-repo-url> tradering
cd tradering
python --version   # >= 3.10
```

## 3. 服务器：冷启动（默认 majors）

```bash
python -m prod.cli bootstrap-server --mode majors
# 等价: python -m prod.bootstrap_server --mode majors
```

会做：

1. 准备 BTC/ETH **15m** → `data/`  
2. seed majors **paper-prep** 注册表（live 关闭）  
3. 写 `reports/prod/server_handoff_contract.json`  

报告：`reports/prod/server_bootstrap.json`

> 若 15m 已存在则跳过下载。首次全量下载可能较慢。

遗留 10U（可选，非晋级路径）：

```bash
python -m prod.cli bootstrap-server --mode ten_u
```

## 4. 服务器：日常（无密钥）

```bash
python -m prod.cli majors-hourly --commit-refresh
python -m prod.cli ops-summary
python -m prod.cli demo-checklist   # 工程 handoff 门槛，非本机下单
```

## 5. 定时任务（Linux cron）

```cron
5 * * * * cd /path/to/tradering && /usr/bin/python3 -m prod.cli majors-hourly --commit-refresh >> /var/log/tradering-majors.log 2>&1
```

锁：`reports/prod/majors_runtime.lock`。

## 6. 密钥与安全（仅服务器 agent）

- 模拟盘/实盘 Key **只放服务器环境**，不要进 Git、不要在开发机配置  
- 启用 demo/live 前先满足 `demo-checklist` 与操作规程  
- **不要**把 live key 配进未审查的自动任务  

## 7. 更新流程

开发机 push → 服务器：

```bash
cd /path/to/tradering
git pull
python -m prod.cli majors-hourly --commit-refresh
```

数据损坏时再 bootstrap；一般不必 `--force-registry`。

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| `blocked_not_in_paper_prep_registry` | `bootstrap-server --mode majors` 或 `admit-majors` |
| 15m 过旧 | `majors-refresh-15m --commit` 或 `majors-hourly --commit-refresh` |
| 需要密钥相关命令 | **仅服务器 agent** 注入 `OKX_*` 后执行 |
| RAVE/LAB | 仅 legacy `ten_u`；不可 demo/live 晋级 |

## 9. 与本机的关系

- **本机**：研发、回测、paper 证据、push  
- **服务器**：bootstrap、定时 majors paper；后期 agent 开 demo/live  
- **状态文件**留在服务器，不要当 Git 同步手段  
