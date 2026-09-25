# ADR-022：V1 性能与响应性稳定 / V1 Performance and Responsiveness Stabilization

- 状态：已接受，W10 实施中 / Status: Accepted; W10 implementation in progress
- 提案日期：2026-09-25 / Proposal date: 2026-09-25
- 接受日期：2026-09-25 / Accepted date: 2026-09-25
- 范围：Workbench W10 / Scope: Workbench W10
- 实施分支：`v1优化`，起点 `0a9de407cfbc2c209dc3e10259f01d845365230a` / Implementation branch: `v1优化`, based on `0a9de407cfbc2c209dc3e10259f01d845365230a`

## 背景 / Context

`v1.0.0-rc.1` 已建立功能闭环和发布身份，但现有实现把大量 Workspace Item
完整投影到 Python 对象，再在 GUI 主线程中全量创建 `QTreeWidgetItem`。搜索先
读全部数据再在内存过滤；Event 先全量读取再截取 300 条；Container 处理和
Export 存在大量逐行 Query、`flush()` 和 Unit of Work。正式基线已证明 10,000
Item Tree/Search 约 5.7 秒、10,000-entry ZIP Inspect 约 108 秒、500 文件
Folder Export 约 71 秒。这些操作虽然可以完成，但不满足日常工作台的
响应性要求。

`v1.0.0-rc.1` established the functional loop and release identity, but the
current implementation projects every Workspace Item into Python objects and
then creates all `QTreeWidgetItem` instances on the GUI thread. Search loads the
whole project before in-memory filtering; Events are fully loaded before being
trimmed to 300; and Container processing and export perform many per-row
queries, `flush()` calls, and units of work. The formal baseline records about
5.7 seconds for a 10,000-item Tree/Search, 108 seconds for a 10,000-entry ZIP
inspection, and 71 seconds for a 500-file folder export. These operations can
finish, but they do not provide acceptable workbench responsiveness.

## 实施前影响 / Pre-implementation Impact

- **Domain**：不改变 Project、Original Snapshot、Source Node、Workspace Item 和 Working
  Artifact 所有权；Cancel 只是操作控制，不成为新业务对象。
- **Flow**：查询、Tree 显示、Processing Persistence 和 Export 改为有界批次与
  增量流；Source 级事务语义保持。
- **State**：复用现有 `INTERRUPTED` 终态表达安全取消；不伪造 `SUCCESS`。
- **Lineage**：保留 Direct Relationship、Origin Binding 和现有 Lineage 事实；只优化
  批量写入与读取。
- **Log**：保留结构化业务 Event；Progress Snapshot 是短期 UI 输出，不代替业务
  Event。
- **Permission**：不扩大文件系统或外部权限；Cancel 不得删除外部输入或已提交
  Original。
- **Tool**：保持现有 typed Application Action/Query；Progress/Cancel 使用明确 Contract，
  但不发布为 MCP Tool。
- **AI / Automation**：不使用 AI，不增加 Agent、MCP、调度器或 Event-driven
  Automation。
- **UI**：Workspace Tree 迁移到 `QTreeView + QAbstractItemModel`，支持按需子节点、
  分批更新和真实进度。

- **Domain**: Project, Original Snapshot, Source Node, Workspace Item, and
  Working Artifact ownership remain unchanged. Cancellation is operation
  control, not a new business entity.
- **Flow**: query, tree presentation, processing persistence, and export become
  bounded batch/incremental flows while retaining Source-level transaction
  semantics.
- **State**: safe cancellation uses the existing `INTERRUPTED` terminal outcome
  and never fabricates `SUCCESS`.
- **Lineage**: direct relationships, origin bindings, and current Lineage facts
  remain; only their bulk write/read paths change.
- **Log**: structured business Events remain. A Progress Snapshot is transient
  UI output and does not replace a business Event.
- **Permission**: no filesystem or external permission expands. Cancellation
  cannot delete external input or committed Original bytes.
- **Tool**: existing typed Application actions/queries remain. Progress and
  cancellation use explicit contracts but are not published as MCP Tools.
- **AI / Automation**: no AI, Agent, MCP, scheduler, or event-driven Automation.
- **UI**: the Workspace Tree moves to `QTreeView + QAbstractItemModel` with lazy
  children, bounded updates, and real progress.

## 决策 / Decisions

### D92：候选版路线 / Candidate Release Route

**采用 A**：`v1.0.0-rc.1` 保持不变；W10 在 `v1优化` 分支实施，通过后
发布 `v1.0.0-rc.2`。不重写已发布 Tag 或资产。

**Adopted A**: keep `v1.0.0-rc.1` immutable, implement W10 on `v1优化`, and
publish `v1.0.0-rc.2` after qualification. Existing tags and assets are not
rewritten.

### D93：Workspace Read Model / Workspace Read Model

**采用 A**：使用 set-based SQL Projection、数据库过滤/排序/分页、批量关联加载
和最近 Event Query。不增加需要同步的 Materialized Read Model 表。

**Adopted A**: use set-based SQL projection, database filtering/sorting/paging,
bulk relation loading, and recent-event queries. Do not add a synchronized
materialized read-model table.

### D94：Workspace Tree UI / Workspace Tree UI

**采用 A**：使用 `QTreeView + QAbstractItemModel`，按需请求 Children，增量刷新受影响
子树。不继续依赖全量 `QTreeWidgetItem` 构建。

**Adopted A**: use `QTreeView + QAbstractItemModel`, request children lazily,
and refresh only affected subtrees. Stop relying on full `QTreeWidgetItem`
construction.

### D95：Processing Persistence / Processing Persistence

**采用 A**：增加批量 Repository 方法，在同一 Source 事务中用有界批次写入
Node、Relationship、Locator、Lineage、Metadata 和 Event。不改变事务原子性。

**Adopted A**: add bulk repository methods and write Nodes, Relationships,
Locators, Lineage, Metadata, and Events in bounded batches within the same
Source transaction. Transaction atomicity remains unchanged.

### D96：后台执行模型 / Background Execution Model

**采用 A**：保留一个后台 Worker 和串行写操作，增加 typed Progress Snapshot 和
文件/Container/批次边界上的 Cooperative Cancel。不建设持久任务平台、
Broker、Pause/Resume 或分布式 Worker。本决策仅覆盖 D60-A/D75-A 的“无
Cancel”限制，其余串行化边界保留。

**Adopted A**: retain one background worker and serialized writes while adding
typed Progress Snapshots and cooperative cancellation at file, Container, and
batch boundaries. Do not build a persistent task platform, broker,
pause/resume, or distributed worker. This supersedes only the no-cancel portion
of D60-A/D75-A; the remaining serialization boundary stays active.

### D97：导入完整性 / Import Integrity

**采用 A**：保留项目内不可变 Original Snapshot、同次 Copy+SHA-256、主动结构发现
和终端延迟物化。不为性能延迟 Hash，不把 Container 发现改为纯 UI 展开时
执行。

**Adopted A**: retain the immutable Project-owned Original Snapshot, single-pass
copy plus SHA-256, eager structure discovery, and lazy terminal materialization.
Do not defer hashing or move Container discovery to UI expansion time.

### D98：性能 Migration / Performance Migration

**采用 A**：允许 `0009_performance_indexes`，但只能增加由 Query Plan 和基准证明有效的
Index；不增加新业务实体、双写或投影表。

**Adopted A**: permit `0009_performance_indexes`, limited to indexes justified
by query plans and benchmarks. It adds no business entity, dual-write path, or
projection table.

### D99：性能验收 / Performance Acceptance

**采用 A**：使用同参考主机的三轮中位数、Peak RSS、SQLite 大小、UI 心跳和
25% 回归门。增加单个 80 MiB 文件与约 2,000 个小文件/合计 80 MiB 的对照
Fixture。这些是参考环境验收，不是跨设备 SLA。

**Adopted A**: use three-run medians on the same reference host, Peak RSS,
SQLite size, UI heartbeat, and a 25% regression gate. Add contrasting fixtures
for one 80 MiB file and about 2,000 small files totaling 80 MiB. These are
reference-environment acceptance gates, not cross-device SLAs.

## 结果 / Consequences

- W10 不更改 V1 产品范围，而是使已有闭环在真实规模下可使用。
- Read Model 和 Qt Model 变更必须通过 typed Application Query，UI 仍不直接访问 SQL。
- Cancel 只在安全检查点生效；原子 Publish/Commit 阶段显示“正在完成”，不强制
  中断。
- 任何优化若需要改变 Original Policy、Source/Workspace 语义或引入持久任务平台，
  必须返回新的重大决策门。

- W10 does not expand V1 scope; it makes the existing loop usable at realistic
  scale.
- Read-model and Qt-model changes still go through typed Application queries;
  the UI never accesses SQL directly.
- Cancellation takes effect only at safe checkpoints. Atomic publish/commit
  stages report that they are finishing and are never forcibly interrupted.
- Any optimization requiring a changed Original policy, altered
  Source/Workspace semantics, or a persistent task platform returns to a new
  major decision gate.
