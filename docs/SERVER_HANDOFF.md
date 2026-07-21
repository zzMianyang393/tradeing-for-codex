# 服务器 Agent Handoff（密钥与 demo/live 仅服务器）

开发机**不**配置 `OKX_*`，**不**跑模拟盘/实盘。  
服务器 agent 拉代码后按本文操作。

机器可读契约：

```bash
python -m prod.cli server-handoff
# → reports/prod/server_handoff_contract.json
```

## 1. 冷启动（默认 majors = BTC/ETH）

```bash
cd /path/to/tradering
git pull
python -m prod.cli bootstrap-server --mode majors
```

会：

1. 确保 `data/BTC_15m.csv`、`data/ETH_15m.csv`（缺则公共接口下载）  
2. 向 `reports/prod/paper_prep_registry.json` 注册 majors paper-prep（`live_allowed=false`）  
3. 写出 `reports/prod/server_handoff_contract.json`  

**不会**写入任何 API Key。

可选遗留 10U（RAVE/LAB，仅 local_experiment）：

```bash
python -m prod.cli bootstrap-server --mode ten_u
# 或 --mode both
```

## 2. 日常（无密钥）

```bash
# 每小时：公共 15m 增量 + 本地 paper
python -m prod.cli majors-hourly --commit-refresh

python -m prod.cli ops-summary
python -m prod.cli status
```

cron 示例见 handoff JSON 的 `cron_example`。

## 3. 后期：模拟盘 / 实盘（仅服务器 agent）

1. agent 注入环境变量（勿进 Git）：
   - `OKX_API_KEY`
   - `OKX_API_SECRET`
   - `OKX_API_PASSPHRASE`
2. 工程门槛（代码侧）：`python -m prod.cli demo-checklist`  
3. 再执行服务器侧 demo/live 流程（策略主循环须另一步晋级，默认关）

## 4. 路径速查

| 用途 | 路径 |
|------|------|
| majors 数据 | `data/*_15m.csv` |
| 注册表 | `reports/prod/paper_prep_registry.json` |
| paper 状态 | `reports/prod/majors_paper_state.json` |
| 锁 | `reports/prod/majors_runtime.lock` |
| handoff | `reports/prod/server_handoff_contract.json` |

## 5. 禁止

- 把交易密钥写进仓库或开发机  
- 用 RAVE/LAB 作为 demo/live 晋级标的  
- 跳过模拟盘见效直接实盘  
