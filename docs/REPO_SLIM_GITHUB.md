# 仓库瘦身与 GitHub 推送

## 问题

当前仓库难推 GitHub 的主因不是 Python 文件太多，而是：

- `data/` 里大量 CSV（单文件数 MB～数 MB×几十）
- `reports/` 里巨型 JSON / jsonl（单个 8–9MB 很常见）
- `pytest_tmp*` 缓存目录
- 历史上这些路径曾被 `git add` 进版本库

## 策略（已采用）

1. **保留本地全部研究文件**（不删你的审计史）
2. **`.gitignore` 忽略** data、reports 大目录、缓存、pyc
3. **Git 只跟踪代码 + 少量文档 + prod 入口**
4. 需要时把数据/报告当本地工件，不进远程

## 本地归档（磁盘瘦身，非 Git）

```powershell
python -m prod.slim_local --archive-root E:\ai-trade\tradering-archive\YYYY-MM-DD
```

默认会把 `reports/candidate_pool`、`data/basis`、`data/calendar_spread*` **move** 到归档目录（保留磁盘，移出工作树）。  
`data/event_trend_v1` 与 `reports/prod` 在保护列表中不会动。

2026-07-17 已执行归档根：`E:\ai-trade\tradering-archive\2026-07-17\`。

## 一次性从 Git 索引移除大目录（不删本地文件）

在项目根目录 PowerShell：

```powershell
powershell -File scripts\slim_git_for_github.ps1
# 或手动：
git rm -r --cached data reports
git add .gitignore prod docs tests/test_prod_*.py scripts/slim_git_for_github.ps1
git status
```

然后 commit（**不需要 force-push**）：

```text
chore: stop tracking data/reports bulk; add production paper-prep track
```

推送：

```powershell
git push origin main
```

若远程历史里已经有大 blob，可能仍需以后 `git filter-repo`——那是可选清理；新提交已不再带 `data/`、`reports/`。

## 推荐远程结构

- 远程：`prod/` + 核心引擎 + tests（可测部分）+ 文档
- 本地：`data/`、`reports/` 完整保留
- 协作者：用 downloader / refresh 自己拉数据
