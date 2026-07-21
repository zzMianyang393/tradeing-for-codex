# 测试卫生只读审查（2026-07-12）

## 审查范围

搜索全部 `tests/` 目录中对以下关键词的断言：
- `candidate`
- `approved_for_paper`
- `safe_to_enable_trading`
- `meta_only`
- `eligible_for_paper`
- `rejected`

## 发现

### 1. 安全闸门断言（应保留）

| 文件 | 行 | 断言 | 类型 |
|---|---|---|---|
| `test_research_approval_registry.py:11` | `assertFalse(registry["safe_to_enable_trading"])` | 全局安全开关 |
| `test_research_approval_registry.py:12` | `assertEqual([], registry["approved_for_paper"])` | 禁止纸上交易 |
| `test_research_approval_registry.py:24` | `assertFalse(record.eligible_for_paper)` | 逐条禁止 |
| `test_research_approval_registry.py:37-67` | 7 个 `assertFalse(eligible_for_paper)` | 逐条禁止 |
| `test_execution_cost_floor_audit.py:31` | `assertEqual("meta_only_not_strategy", report["decision"])` | 元研究标签 |
| `test_low_turnover_research_gate.py:32` | `assertEqual("meta_only_not_strategy", report["decision"])` | 元研究标签 |

**评估：** 这些是关键安全闸门，防止任何策略被错误批准。必须保留。

### 2. 策略状态断言（可能需泛化）

| 文件 | 行 | 断言 | 评估 |
|---|---|---|---|
| `test_donchian_atr_trend_baseline_audit.py:113` | `assertEqual("rejected", verdict["status"])` | 硬编码 rejected | 当前正确，未来新方向可能不同 |
| `test_oi_independent_change_audit.py:58` | `assertEqual("rejected", verdict["status"])` | 同上 | 同上 |
| `test_range_regime_mean_reversion_audit.py:107` | `assertEqual("rejected", verdict["status"])` | 同上 | 同上 |

**评估：** 这些断言验证特定已淘汰策略的状态。如果未来重新运行这些审计脚本（不应发生），断言仍然正确。但如果需要为新方向复用测试框架，这些硬编码值需要泛化。当前无需修改。

### 3. 候选管道测试（非安全相关）

| 文件 | 行 | 断言 | 评估 |
|---|---|---|---|
| `test_candidate_pipeline.py:72` | `assert len(longs) >= 1` | 候选扫描功能测试 | 非安全相关 |
| `test_candidate_pipeline.py:120` | `assert len(cands) == 0` | 无候选情况 | 非安全相关 |
| `test_candidate_pipeline.py:281` | `assert passed` | 过滤器通过 | 非安全相关 |

**评估：** 这些是候选管道的功能测试，不涉及安全闸门。如果候选管道被弃用，这些测试可以删除。

### 4. 其他引用

| 文件 | 行 | 内容 | 评估 |
|---|---|---|---|
| `test_backtester_risk_profile.py:15` | `regime="candidate"` | 测试用例参数 | 无害，仅为测试数据 |
| `test_funding_proxy_strategy.py:23` | `assertEqual("candidate_funding_crowding_reversal", ...)` | 旧策略名 | 可能过时 |
| `test_goal_search.py` | 多行 | `candidates` 变量名 | 通用变量名，非安全相关 |

## 总结

| 类别 | 数量 | 建议 |
|---|---|---|
| 安全闸门断言 | 10 | **保留** |
| 硬编码策略状态 | 3 | 保留（当前正确，未来可能需泛化） |
| 候选管道功能测试 | ~10 | 保留（如管道弃用可删除） |
| 通用变量名引用 | ~5 | 无害 |

## 结论

当前测试体系中**没有发现需要立即修复的问题**。

安全闸门断言（`safe_to_enable_trading=false`、`approved_for_paper=[]`、`eligible_for_paper=false`）全部正确且必要。

硬编码的 `"rejected"` 状态断言在当前上下文中正确，但如果未来需要为新方向复用审计测试框架，需要将状态断言参数化。

## 禁止事项

- 不修改测试
- 不运行全量测试（本审查为只读）
- 不删除安全闸门断言
