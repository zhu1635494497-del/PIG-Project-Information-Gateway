# 持久化与可靠性规则 / Persistence and Reliability Rules

适用：数据库、文件发布、外部编辑、版本、恢复、并发、日志和性能。
已有设计以当前有效 ADR 为准；本文件补充验收要求，不宣称未验证能力已经实现。

Applies to databases, file publication, external editing, versions, recovery, concurrency,
logging, and performance. Active ADRs govern existing design; these requirements do not certify
unverified capabilities as implemented.

## 1. 跨介质写入 / Writes across storage boundaries

**MUST** 为新关联项目的 Revision 捕获及旧 Workbench 的导入、物化、版本轮换、
撤销导入和导出分别明确：操作身份、Staging 所有权、校验、发布、数据库提交、
失败补偿和重启恢复。建立纯路径关联不产生文件副本。
文件系统操作与 SQLite 事务不会天然形成一个原子事务。

**MUST** define operation identity, staging ownership, verification, publication, database commit,
failure compensation, and restart recovery for new Revision capture and historical import,
materialization, rotation, undo, and export. A path-only link creates no file copy. Filesystem
actions and SQLite transactions are not naturally one atomic transaction.

**MUST** 使用已批准的版本化 Staging Manifest 和 Recovery 机制表达跨介质证据；
需要原子发布的操作在目标卷暂存，校验字节后发布。持久化语义和 flush/fsync/rename
限制必须按目标系统验证，不能以进程内异常测试冒充断电安全保证。

**MUST** use the accepted versioned staging manifest and recovery mechanism for cross-storage
evidence. Stage atomic publications on the destination volume and verify bytes before publishing.
Verify durability and flush/fsync/rename constraints on the target system; in-process exception
tests alone do not establish power-loss guarantees.

**MUST** 验证写入中断、发布成功但落库失败、部分移动和清理失败的处理。
恢复依据操作类型与数据库事实，不能仅按目录名统一删除。扫描是只读；执行恢复
遵守 ADR-020 的确认与 Working 保护边界。需要恢复时阻止冲突写入并说明原因。

**MUST** verify interrupted writes, publication followed by commit failure, partial moves, and
cleanup failure. Recovery uses operation type and database facts, not directory-name deletion.
Scanning is read-only; recovery follows ADR-020 confirmation and Working protection. Block
conflicting writes when recovery is required and explain why.

## 2. SQLite 与升级 / SQLite and upgrades

**MUST** 显式检测模型/Schema 版本；新代码默认只需支持用新代码创建的项目。旧版
项目数据库无需兼容或迁移，除非负责人对具体版本单独授权；不支持时明确拒绝，
不得静默重建或改写旧数据。若另行批准迁移，才按 ADR-025 先确认、备份并校验，
再执行受控 Alembic 前向 Migration 与事实检查；失败保留备份并停止写入。

**MUST** detect model/schema versions. New code only needs to support projects created by
that code by default. Compatibility or migration for older project databases requires
separate owner authorization for the specific versions. Reject unsupported databases
explicitly; never silently rebuild or rewrite them. If migration is separately approved,
follow ADR-025: confirm, back up and verify, run controlled Alembic forward migration,
and validate facts. Retain the backup and stop writes on failure.

**MUST** 定义事务边界、外键/唯一约束和连接级设置；不可依赖 UI 校验维持完整性。
备份必须获取一致数据库视图；WAL 模式下不得仅复制活动 `project.sqlite` 而漏掉
未 checkpoint 的内容。索引重建不得修改 Original、Working 或 Context Revision 字节。

**MUST** define transaction boundaries, foreign-key/unique constraints, and connection settings;
UI validation alone cannot ensure integrity. Backups require a consistent database view; in WAL
mode, copying only an active `project.sqlite` may omit uncheckpointed data. Index rebuilding
cannot modify Original, Working, or Context Revision bytes.

**SHOULD** 根据现有串行写入和测量选择 WAL、busy timeout 与查询索引；新增索引
应由 Query Plan 和基准支持。支持多实例或更改写入模型须明确决策；不得出现静默
Last-write-wins。记录当前多实例限制，不把未测试情形宣称为支持。

**SHOULD** choose WAL, busy timeout, and indexes from current serialized writes and measurements.
Use query plans and benchmarks to justify indexes. Multi-instance support or a changed write
model requires an explicit decision; no silent last-write-wins. Document untested limitations.

## 3. 外部编辑与版本 / External edits and versions

新关联项目 **MUST** 在显式刷新、打开前及按需固定前观察稳定 Size/SHA-256；
可在窗口重新获得焦点时检查当前选中项。不得声称捕获每次 Host Save。旧 Workbench
继续按 ADR-016/018 的既有检查点执行。
未检测的中间保存不保证存在。读取稳定性重试必须有界，失败显示明确状态。

New linked projects **MUST** observe stable size/SHA-256 at explicit refresh, before open,
and before on-demand capture; focus return may inspect the selected item. Do not claim every
host save is captured. The historical Workbench retains ADR-016/018 checkpoints. Intermediate
saves are not guaranteed; stability retries are bounded.

旧 Workbench **MUST** 保持 Current/Previous 与内部校验副本的语义，轮换成功前保护可恢复旧字节；
回滚须确认并把被覆盖 Current 交换为 Previous。`MISSING/UNREADABLE` 保留最后成功
Fingerprint 并显式报告，不用陈旧状态或 Original 冒充当前文件。

The historical Workbench **MUST** preserve current/previous/checkpoint semantics and recoverable old bytes until successful
rotation. Confirm rollback and swap the replaced current into previous. Missing/unreadable
states retain the last successful fingerprint and are explicit, never disguised by stale or Original bytes.

**MUST** 区分检测、冲突和恢复。外部文件被占用、改名、删除或在读取期间变化时，
返回可理解结果；PIG 不覆盖未知新编辑。项目外 Save As 不自动追踪；Watcher、
Diff/Merge、完整版本历史不是本文件授权的新增能力。

**MUST** distinguish observation, conflict, and recovery. Locked, renamed, deleted, or unstable
files return understandable results without replacing unknown edits. External Save As is not
tracked automatically; this file does not authorize watchers, merge, or full history.

Context 的 `context_revision` 与 Workspace 的 `workspace_revision` 分离；Context 写入
和捕获须检查各自预期状态，冲突不得静默覆盖。Context 保留遵守 ADR-025，不套用
Working 的两个版本上限。

Keep `context_revision` separate from `workspace_revision` and validate expected state for
Context writes and captures. No silent conflict overwrite. Context retention follows ADR-025,
not the Working two-version limit.

## 4. 状态、事件与日志 / States, events, and logs

**MUST** 将当前状态与追加业务事件分离，并保证关键状态变更和事件一致；操作内
瞬态不必全部持久化。错误结果至少表达对象、阶段、稳定错误码、安全信息和是否可重试。
现有 ADR 要求的 Event 必须保留，不能以降低日志量为由直接删除。

**MUST** separate current state from append-only business events and keep key changes consistent.
Transient operation phases need not all be persisted. Errors identify object, stage, stable code,
safe message, and retryability. Retain events required by accepted ADRs.

**SHOULD** 区分业务事实、审计需求、短期 Progress/Telemetry 和 Debug Log。
高频进度不逐条永久落库；诊断日志配置容量与保留周期。业务历史的裁剪或清理须有
明确保留策略，不能损害来源、恢复证据或仍有效的 Revision 引用。

**SHOULD** distinguish business facts, audit needs, transient progress/telemetry, and debug logs.
Do not persist every progress tick. Bound diagnostic capacity and retention. Pruning business
history needs a defined policy that protects origin, recovery evidence, and active revision references.

## 5. 响应性与性能证据 / Responsiveness and performance evidence

**MUST** 将耗时 I/O、Hash、解析、捕获与导出移出 UI 主线程；提供真实进度、安全
取消点和串行受控写入。提交/原子发布阶段显示正在完成，不强制中断。列表和搜索
应该使用分页、按需子节点和有界查询，避免全量读取后过滤。

**MUST** keep costly I/O, hashing, parsing, capture, and export off the UI thread with truthful
progress, safe cancellation, and serialized controlled writes. Let atomic publication/commit
finish without forced interruption. **SHOULD** use pagination, lazy children, and bounded queries.

**MUST** 对性能相关改动使用可重复 Fixture 和参考环境；沿用 ADR-020/022 的三轮
中位数、Peak RSS、SQLite 大小、UI 心跳与同环境超过 25% 的回归门，不能作为
跨设备 SLA。新内容提取/搜索的延迟、内存、临时磁盘和取消预算须在对应阶段制定
并测量；此处不编造尚未批准的绝对秒数或资源数值。

**MUST** use reproducible fixtures and a reference environment for performance changes. Retain
ADR-020/022 three-run medians, peak RSS, database size, UI heartbeat, and the greater-than-25%
same-environment regression gate, not a cross-device SLA. Define and measure extraction/search
latency, memory, temporary-disk, and cancellation budgets in the relevant milestone.
