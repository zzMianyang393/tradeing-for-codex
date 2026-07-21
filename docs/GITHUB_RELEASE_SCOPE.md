# GitHub 发布范围

本仓库的 GitHub 版本只承载可复现的生产主链、核心交易引擎、核心测试和必要的运行文档。

## 纳入 GitHub

- `prod/`：准入、BTC/ETH production-bound paper、状态、锁、恢复、运维摘要和服务器交接代码
- `runner.py`、`exchange.py`、`executor.py`、`risk_manager.py`、`state_db.py`：执行与风控底座
- 核心回测、行情下载和验证模块
- `tests/`：核心回归测试
- `docs/PRODUCTION_TRACK.md`、`docs/SERVER_DEPLOY.md`、`docs/SERVER_HANDOFF.md`、本文件及必要的路线文档
- `scripts/`：服务器和本地定时运行脚本

## 不纳入 GitHub

- `data/`：本地行情、资金费率和其他市场数据
- `reports/`：本地回测、paper 状态、运行报告和数据库
- `__pycache__/`、`.pytest_cache/`、临时文件、日志、锁文件
- 大型候选池、JSONL 数据和 HTML 研究快照
- 研究实验脚本和历史审计报告；它们保留在本地工作区或单独归档，不作为生产发布依赖

## 当前发布基线

- 默认运行模式：`local_paper`
- 生产候选宇宙：`BTC-USDT-SWAP`、`ETH-USDT-SWAP`
- 默认起始权益：10 USDT；资本敏感性上限：500 USDT
- 当前唯一 production-bound paper-prep 策略：
  `prod_majors_h1_high_vol_donchian_short_v1`
- GitHub 发布不代表模拟盘或实盘授权
- API key、`.env` 和服务器运行状态永远不进入 Git

## 发布前检查

```bash
python -m prod.cli --help
python -m compileall -q prod runner.py exchange.py executor.py risk_manager.py state_db.py
python -m prod.cli server-handoff
python -m prod.cli demo-checklist
```

完整测试应在服务器或 CI 中单独运行；本地 `reports/` 和 `data/` 不是发布输入。
