# Hermes 研究运行协议

本协议用于让服务器上的 Hermes agent 继续研究，同时保持生产主链可控。

## 目标

Hermes 可以运行、比较和记录研究结果，但不能未经人工确认修改生产策略、启用交易所下单或把研究结果自动晋级为 paper/demo/live。

## 每次研究前

1. `git pull --ff-only` 获取最新代码。
2. 确认当前分支和 commit；生产运行只能使用已标记版本。
3. 确认 `data/` 已存在且数据时间覆盖满足研究窗口。
4. 阅读 `docs/research_protocol_v1.md`、`docs/research_risk_map_2026-07-13.md` 和当前策略状态文档。
5. 研究默认使用 BTC/ETH 固定宇宙、10 USDT 起始权益和含成本模型。

## 研究约束

- 不从多币结果中事后挑选赢家币。
- 不修改已经冻结的生产策略参数来改善结果。
- 不把单窗口、单币、单笔交易或未扣成本结果当作 alpha 证据。
- 必须检查前视偏差、时间戳对齐、数据覆盖、手续费、滑点和资金费率。
- 新候选必须先经过独立验证，再进入 `prod/` 准入流程。
- 研究代码可以提交 Git；大数据、报告、日志和运行状态不提交 Git。

## 输出规范

每次研究至少生成：

- 一个可复现的 Python 入口
- 一个 Markdown 研究摘要，说明假设、数据窗口、宇宙、成本和结论
- 一个机器可读 JSON 结果，保存在服务器 `reports/`，不提交 Git
- 明确结论：`rejected`、`watchlist`、`paper_prep_candidate` 或 `not_validated`

研究摘要必须写清楚：

- 是否样本外
- 是否跨年份/跨窗口
- 是否包含交易成本
- 收益是否集中在单币、单月或单笔交易
- 为什么通过或拒绝
- 如果要进入 `prod/`，需要哪些人工确认

## Git 工作流

- 研究代码和研究摘要提交到 `research` 分支或独立 feature 分支。
- 生产主链只从人工确认后的提交进入 `main` 或发布 tag。
- 不使用 `git add -A`，避免把 `data/`、`reports/` 和临时产物带入提交。
- 提交前运行：

```bash
python -m prod.cli --help
python -m compileall -q prod runner.py exchange.py executor.py risk_manager.py state_db.py
python -m pytest -q tests/test_prod_policy.py tests/test_prod_graduation.py tests/test_prod_ops_and_halt.py
```

## Hermes 禁止事项

- 不配置或读取开发机上的交易密钥。
- 不自动执行 OKX demo/live 下单。
- 不修改 `prod/` 中的冻结策略并声称已经重新验证。
- 不删除历史研究证据。
- 不把 `reports/` 运行结果当作 Git 版本同步机制。

## 服务器运行目录

建议服务器保留：

```text
tradering/              # Git checkout：源码和文档
tradering-data/         # 行情和其他本地数据
tradering-reports/      # 回测、paper、研究结果和日志
```

这样 Hermes 可以通过 Git 同步代码，通过本地目录保存数据和结果，不会污染 Git 历史。
