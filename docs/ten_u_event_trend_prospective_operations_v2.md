# 10U Event Trend v2 前瞻观察运行约束

## 正式观察边界

- 开始：`2026-07-16T00:00:00Z`
- 最早验收：`2026-10-14T00:00:00Z`
- 币种：`RAVE-USDT-SWAP`、`LAB-USDT-SWAP`、`ETH-USDT-SWAP`
- 策略配置指纹：`d20986a5c15aef78272f5b3d11ef200f57f110e1b714dc8115bb097ac98df116`
- 观察阶段只保存信号，不读取或写入退出价格、PnL、MFE、MAE、胜负和权益。

## 每小时刷新

在项目目录运行：

```text
python ten_u_event_trend_refresh_v2.py
```

Codex 本地自动化 `10U prospective hourly refresh` 已启用，每个整点后第 10 分钟运行。项目根目录只执行一个固定入口：`python tradering\ten_u_event_trend_cycle_v2.py`。该入口自行切换到策略工作目录，串行执行刷新、健康检查和安全摘要；自动化禁止运行验收器、修改策略或查看信号后的行情结果。刷新器使用原子锁 `reports/ten_u_event_trend_refresh_v2.lock` 防止两个任务同时写账本，45分钟以上的遗留锁才允许回收。

自动化工具调用固定使用 `cmd.exe`、`login=false` 和默认沙箱。默认 PowerShell 在自动任务沙箱中曾出现 Windows error 5，因此禁止自动任务退回 PowerShell或请求提权。真实调度验证证据保存在 `reports/ten_u_event_trend_automation_verification_v2.json`。

刷新器只接受 OKX 已确认收盘的 1H K 线。原有 K 线的字段或哈希发生变化时停止；时间缺口、重复时间戳和未确认 K 线也会停止。

同一次刷新还会从 OKX `funding-rate-history` 追加已经实际结算的资金费率。历史同时间记录发生变化、间隔超过 8 小时、出现未来费率或最新结算点距离 K 线截止超过 8 小时时停止。每个币的资金费率路径、SHA-256、最大间隔及截止滞后均绑定到动态数据清单；正式验收拒绝使用未绑定或哈希漂移的费率文件。

## 信号首次可见性

触发 K 线收盘时，下一小时开盘的入场提案已经可知，不等待下一根 K 线收盘。正式账本记录同时保存：

- `entry_time`：计划入场时点；
- `observed_at`：系统首次因果可见时点。

两者必须完全相等。刷新中断后才发现的旧信号记为 `late_signal_records_rejected`，不得事后补入正式前瞻账本。这样会牺牲样本数量，但避免将已经走出部分结果的信号伪装为实时信号。

## 不可覆盖审计

- 信号账本：`reports/ten_u_event_trend_prospective_ledger_v2.json`
- 最新刷新摘要：`reports/ten_u_event_trend_prospective_refresh_v2.json`
- 刷新审计链：`reports/ten_u_event_trend_prospective_refresh_audit_v2.json`
- 运行健康状态：`reports/ten_u_event_trend_health_v2.json`
- 小时安全摘要：`reports/ten_u_event_trend_cycle_v2.json`

刷新审计链为逐条 SHA-256 链。修改任意旧记录都会使后续 `previous_hash` 或最终 `head_hash` 校验失败。

除记录哈希链外，每次刷新还必须满足跨次语义连续性：本次 `manifest_sha256_before` 等于上次 `manifest_sha256_after`，本次 `ledger_head_hash_before` 等于上次 `ledger_head_hash_after`，已有资金费率的本次 before 哈希等于上次 after 哈希，且数据截止时间不得倒退。刷新器会在下载或写入任何数据之前检查这些关系；同时修改数据文件和清单、回滚账本或替换费率历史都会直接停止。

健康检查要求K线、资金费率、账本、刷新审计链和验收器源码指纹同时通过，并要求市场数据与最近刷新记录不超过2小时。健康检查不计算任何收益指标。

## 验收纪律

90 天只是时间下限，不足 6 笔正式、准时记录的交易仍不验收。验收前不得根据前瞻期间的行情修改方向规则、持续确认根数、回踩等待时间、止损、持有时间、仓位或门槛。迟到信号不计入交易数，也不用于补足最低样本。

## 封存验收器

验收实现和依赖源文件的 SHA-256 已在尚无正式信号时冻结：

- 注册：`reports/ten_u_event_trend_evaluator_registration_v2.json`
- 程序：`ten_u_event_trend_evaluation_v2.py`
- 状态报告：`reports/ten_u_event_trend_prospective_evaluation_v2.json`

验收器先只读取注册、信号账本和刷新审计链。以下条件全部满足前，不得打开行情结果或资金费率文件：

1. 当前时间不早于 `2026-10-14T00:00:00Z`；
2. 正式观察数据覆盖不早于该时间；
3. 至少 6 条准时信号已经拥有完整 48 小时结果窗口。

解封后仍以实际成交数为准。若重叠持仓、最小合约限制或止损距离过滤导致实际成交不足 6 笔，状态为 `prospective_insufficient_executed_trades`，继续观察而不判成功。实际成交达到 6 笔后，第一次成熟验收具有约束力：通过才进入模拟盘；失败则淘汰 v2，不允许用参数修改挽救。

扫止损、盈利捕获和可执行权益峰值的精确定义见 `docs/ten_u_event_trend_metric_audit_v2.md`。这些口径在正式前瞻信号仍为 0 条时冻结，并已写入验收器规格指纹。
