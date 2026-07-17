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

## 一次性从 Git 索引移除大目录（不删本地文件）

在项目根目录 PowerShell：

```powershell
# 仅从 git 索引移除，磁盘文件保留
git rm -r --cached data reports pytest_tmp* 2>$null
git rm -r --cached --ignore-unmatch __pycache__

# 确认 .gitignore 已保存后
git add .gitignore prod docs/PRODUCTION_TRACK.md docs/REPO_SLIM_GITHUB.md
git status
```

然后单独做一次 commit，例如：

```text
chore: stop tracking data/reports bulk; add production paper-prep track
```

推送：

```powershell
git push origin main
```

若远程已有巨大历史，可能仍需 `git filter-repo` 清历史——那是另一步；先保证**新提交不再带大数据**。

## 推荐远程结构

- 远程：`prod/` + 核心引擎 + tests（可测部分）+ 文档
- 本地：`data/`、`reports/` 完整保留
- 协作者：用 downloader / refresh 自己拉数据
