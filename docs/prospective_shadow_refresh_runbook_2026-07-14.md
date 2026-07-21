# 前瞻影子账本刷新操作手册（2026-07-14）

## 默认模式：dry-run

所有刷新操作默认为 dry-run。dry-run 模式下：
- 生成 staging 报告到 `reports/staging/`
- 执行 append-only 验证
- 输出 `refresh_decision=ready_to_commit` 或 `rejected`
- **不覆盖正式报告**
- **不更新 checkpoint**

```bash
# dry-run（默认）
python prospective_shadow_refresh_pipeline.py
```

## 何时可以 --commit

仅当以下条件全部满足时才可使用 `--commit`：

1. dry-run 输出 `refresh_decision=ready_to_commit`
2. `append_validation.valid=true`
3. `integrity_status=valid`
4. 新 observation 的 signal_ts > checkpoint 最大 signal_ts
5. 所有 28 条既有 observation 字段完全一致

```bash
# commit（仅当 dry-run 通过后）
python prospective_shadow_refresh_pipeline.py --commit
```

## staging 拒绝后的处理

如果 dry-run 输出 `rejected`：

1. 检查 `reject_reasons` 中的具体原因
2. **不得手工编辑 checkpoint 或正式报告**
3. 修复信号生成逻辑后重新 dry-run
4. 不得通过修改 checkpoint 来绕过验证

## 禁止事项

- **不得手工编辑 checkpoint**：checkpoint 只能通过管线自动更新
- **不得删除既有 observation**：append-only 约束
- **不得回填旧时间的 observation**：新 signal_ts 必须 > checkpoint max
- **不得在 dry-run 通过前使用 --commit**
- **刷新只是记录新信号，不是评估结果，更不是交易许可**

## 事务发布机制

发布使用**带回滚的事务发布**（不是文件系统原子多文件替换）。

### 发布流程

1. **备份**：为 ledger、registry、maturity、integrity、checkpoint 五份正式文件创建同目录 `.bak` 备份
2. **暂存**：所有 staging 文件和新 checkpoint 先写入 `.tmp` 临时文件
3. **替换**：逐个 `os.replace` 替换正式文件
4. **验证**：确认五份文件全部存在

### 失败回滚

如果任一 `os.replace` 失败：

1. 恢复此前已替换的正式文件（从 `.bak` 备份）
2. 删除本次新建但原本不存在的目标文件
3. 清理所有 `.tmp` 临时文件
4. 验证五份正式文件与提交前字节一致
5. 输出 `published=false, rollback_attempted=true, rollback_succeeded=true/false`

**重要**：这不是文件系统原子操作。在替换过程中，文件可能处于中间状态。回滚确保最终状态与提交前一致，但不保证中间状态的原子性。

## 管线阶段

```
1. 加载 checkpoint（或从 registry 初始化）
2. 加载源 ledger（staging 或当前正式）
3. 生成 staging registry
4. 生成 staging maturity audit
5. 生成 staging integrity audit
6. append-only 验证
7. decision = ready_to_commit / rejected
8. （仅 --commit 且 valid）原子替换正式报告 + 更新 checkpoint
```

## checkpoint 结构

```json
{
  "checkpoint_type": "prospective_observation_checkpoint",
  "version": "1.0.0",
  "genesis_count": 28,
  "current_count": 28,
  "max_signal_ts": 1783915200000,
  "identities": {
    "hash1": {"observation_id": "hash1", "candidate_id": "...", ...},
    ...
  }
}
```

- `genesis_count`：初始 28 条，永远不变
- `current_count`：当前总观察数（>= genesis_count）
- `max_signal_ts`：当前最大 signal_ts（单调递增）
- `identities`：全量已发布 observation 的 identity 映射

## 刷新频率建议

- 建议每日或每周刷新一次
- 刷新前先 dry-run 确认无问题
- 刷新后运行 `prospective_refresh_publish_audit.py` 验证一致性
