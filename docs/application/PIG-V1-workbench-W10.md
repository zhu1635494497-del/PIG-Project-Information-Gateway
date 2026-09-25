# PIG V1 Workbench W10 性能与响应性稳定 / Performance and Responsiveness Stabilization

- 状态：已批准，实施中 / Status: Approved; implementation in progress
- 日期：2026-09-25 / Date: 2026-09-25
- 决策：`ADR-022`，D92-A 至 D99-A / Decisions: `ADR-022`, D92-A through D99-A
- 分支：`v1优化` / Branch: `v1优化`
- 基线：`0a9de407cfbc2c209dc3e10259f01d845365230a` (`v1.0.0-rc.1`) / Baseline: `0a9de407cfbc2c209dc3e10259f01d845365230a` (`v1.0.0-rc.1`)
- 目标候选版：`v1.0.0-rc.2` / Target candidate: `v1.0.0-rc.2`

## 目标 / Goal

在不改变 V1 文件工作台语义、Original/Working 完整性和 Source/Workspace 边界的
前提下，消除大量小文件、大型 Container、大树和批量导出的主要卡顿。用户在
长操作中必须能看到真实阶段、进度和可用的安全取消入口；GUI 不得因全量
Widget 构建长时间停止响应。

Remove the primary stalls caused by many small files, large Containers, large
trees, and bulk export without changing V1 workbench semantics,
Original/Working integrity, or the Source/Workspace boundary. Long operations
must expose real stages, progress, and a safe cancellation path; the GUI must
not stop responding because it constructs every widget eagerly.

## 非目标 / Non-goals

- 不延迟 Original SHA-256，不修改外部输入。
- 不把主动 Container 结构发现改为纯 UI 展开时处理。
- 不增加 Redis、Broker、微服务、分布式 Worker 或持久 Pause/Resume。
- 不实施 V2 Content Index、OCR、AI、Agent 或 MCP。
- 不重写 `v1.0.0-rc.1`。

- Do not defer Original SHA-256 or modify external input.
- Do not replace eager Container discovery with UI-expansion-only processing.
- Do not add Redis, a broker, microservices, distributed workers, or persistent
  pause/resume.
- Do not implement V2 Content Index, OCR, AI, Agents, or MCP.
- Do not rewrite `v1.0.0-rc.1`.

## W10.1：Read Model 与虚拟化 Tree / Read Model and Virtualized Tree

- **目标 / Goal**：打开、刷新、搜索和展开大型 Workspace 时保持 GUI 响应。 /
  Keep the GUI responsive while opening, refreshing, searching, and expanding a
  large Workspace.
- **输入 / Input**：10,000 Item Project，包含 Active、Deleted、Virtual、Materialized 和
  Modified Item。 / A 10,000-item Project containing active, deleted, virtual,
  materialized, and modified items.
- **核心实现 / Core work**：set-based Workspace Projection；SQL Filter/Sort/Page；最近
  Event Limit；`QTreeView + QAbstractItemModel`；Lazy Children；增量子树刷新。 /
  Set-based projection, SQL filtering/sorting/paging, bounded recent Events,
  `QTreeView + QAbstractItemModel`, lazy children, and incremental subtree
  refresh.
- **数据落库 / Persistence**：原则上只读；如 Query Plan 证明需要，通过 `0009`
  增加 Index。 / Read-only by default; add indexes through `0009` only
  when justified by query plans.
- **测试 / Tests**：Projection 等价性、SQL 数量上限、分页稳定性、Lazy Fetch、选中保持、
  Drag/Drop、Deleted Items、UI Heartbeat。 / Projection equivalence,
  bounded query count, stable paging, lazy fetch, selection preservation,
  drag/drop, Deleted Items, and UI heartbeat.
- **验收 / Acceptance**：同参考主机 10k Tree Query 中位数不高于 1.5 秒，Search
  首页不高于 0.75 秒；Tree 不全量创建 Qt Item；单次 GUI 同步批次不超过
  100 ms。 / On the reference host, median 10k Tree query is at most 1.5
  seconds and first Search page at most 0.75 seconds; the Tree does not create
  every Qt item eagerly; no synchronous GUI batch exceeds 100 ms.

## W10.2：Import 与 Processing Persistence / Import and Processing Persistence

- **目标 / Goal**：降低大量 Node 的 Python/SQLite 固定成本。 / Reduce fixed Python
  and SQLite cost for large node counts.
- **输入 / Input**：2,000 文件 Snapshot、10,000-entry ZIP 和混合嵌套 Container。 /
  A 2,000-file Snapshot, 10,000-entry ZIP, and mixed nested Containers.
- **核心实现 / Core work**：Plan ID Map；批量 Repository；同一 Source 事务内的有界
  `executemany`/批量 ORM 写入；批量 Lineage/Event；去除重复 Parent/Source/Backend Query。 /
  Plan ID maps, bulk repositories, bounded `executemany`/ORM batches inside one
  Source transaction, bulk Lineage/Events, and removal of repeated
  parent/source/backend queries.
- **数据落库 / Persistence**：事实、状态、Relationship、Lineage 和 Event 语义不变。 /
  Fact, state, Relationship, Lineage, and Event semantics do not change.
- **测试 / Tests**：批量与单条结果等价；中途失败整个 Source 回滚；Sibling 继续；
  Duplicate/Traversal/Limit/Encrypted 结果不变。 / Bulk/single-result
  equivalence, whole-Source rollback on failure, sibling continuation, and
  unchanged duplicate/traversal/limit/encryption outcomes.
- **验收 / Acceptance**：2k Snapshot 中位数不高于 8.5 秒；10k ZIP Inspect 不高于
  35 秒；Peak RSS 不高于 300 MiB。 / Median 2k Snapshot is at most
  8.5 seconds; 10k ZIP inspection at most 35 seconds; Peak RSS at most 300 MiB.

## W10.3：Export 与 Working File Pipeline / Export and Working File Pipeline

- **目标 / Goal**：批量导出不再为每个文件创建独立读事务和无条件 Hash。 /
  Avoid one read transaction and unconditional hash per exported file.
- **输入 / Input**：500 个已物化/未物化文件，普通文件夹导出与多选 ZIP。 /
  500 materialized/unmaterialized files for directory and multi-selection ZIP
  export.
- **核心实现 / Core work**：批量 Artifact Projection；稳定相对路径预计算；只对可能变化
  的 Working File 执行受限内容校验；流式写入与 Progress。 / Bulk artifact
  projection, precomputed stable relative paths, bounded content verification
  only for potentially changed Working Files, streaming writes, and progress.
- **数据落库 / Persistence**：保留 Export Requested/Completed/Failed 与 Working 变化事实。 /
  Preserve Export Requested/Completed/Failed and Working-change facts.
- **测试 / Tests**：Modified/Missing/Unreadable、Collision、Empty Folder、Replace Confirmation、
  中途失败原子清理。 / Modified/missing/unreadable files, collisions,
  empty folders, replacement confirmation, and atomic cleanup on failure.
- **验收 / Acceptance**：同参考主机 500 小文件 Folder Export 不高于 25 秒，ZIP
  Export 不高于 13 秒。 / On the reference host, 500-small-file
  folder export is at most 25 seconds and ZIP export at most 13 seconds.

## W10.4：Progress、Cancel 与 Resource Preflight / Progress, Cancel, and Resource Preflight

- **目标 / Goal**：长操作可观察、可安全停止，并在开始前拦截明显的磁盘/规模风险。 /
  Make long operations observable and safely cancellable, and reject obvious
  disk/scale risk before work starts.
- **输入 / Input**：单个 80 MiB 文件、约 2,000 文件/合计 80 MiB 的文件夹、大型
  Archive 与磁盘余量不足。 / One 80 MiB file, about 2,000 files
  totaling 80 MiB, a large archive, and insufficient free space.
- **核心实现 / Core work**：typed Progress Snapshot；Stage/Count/Bytes/Current Item；安全
  Cancellation Token；Preflight Count/Size/Free Space；超大输入软警告。 / Typed
  Progress Snapshots, stage/count/bytes/current item, safe cancellation tokens,
  count/size/free-space preflight, and soft warnings for oversized input.
- **数据落库 / Persistence**：Progress 不落库；安全取消使用 `INTERRUPTED` 和现有结构化
  Event；已提交 Original/Working 不回滚为未记录状态。 / Progress is
  transient; safe cancellation uses `INTERRUPTED` and current structured Events;
  committed Original/Working bytes never become unrecorded state.
- **测试 / Tests**：每个安全检查点取消；Atomic Publish/Commit 期间延迟取消；重启
  Recovery；进度单调性；磁盘预检。 / Cancellation at every safe
  checkpoint, deferred cancellation during atomic publish/commit, restart
  recovery, monotonic progress, and disk preflight.
- **验收 / Acceptance**：拖入后 500 ms 内出现阶段反馈；长操作期间窗口可移动/重绘；
  Cancel 在下一安全点生效且项目可重开。 / Stage feedback appears within
  500 ms after a drop; the window remains movable/repaintable; cancellation
  takes effect at the next safe checkpoint and the Project reopens cleanly.

## W10.5：Qualification 与 RC.2 / Qualification and RC.2

- **目标 / Goal**：证明优化不破坏业务完整性，并形成可回归的性能证据。 /
  Prove that optimization preserves business integrity and creates repeatable
  performance evidence.
- **输入 / Input**：W10.1–W10.4 闭环、W8 Baseline、真实非敏感测试资料。 /
  Completed W10.1-W10.4, the W8 baseline, and real non-sensitive fixtures.
- **核心实现 / Core work**：新基准、新旧比较、Query Plan 证据、源码与打包桌面验收、
  `v1.0.0-rc.2` 发布准备。 / New baseline, old/new comparison, query-plan
  evidence, source and packaged desktop acceptance, and `v1.0.0-rc.2` release
  preparation.
- **数据落库 / Persistence**：无新业务实体；只保存 Migration、Benchmark 和 Release
  Evidence。 / No new business entity; only migrations, benchmarks, and
  release evidence.
- **测试 / Tests**：全量回归、Migration `0001 -> head`、Package Smoke、Recovery、真实拖入/搜索/
  打开/导出。 / Full regression, `0001 -> head` migration, package smoke,
  recovery, and real drag/search/open/export.
- **验收 / Acceptance**：所有 W10 指标达成；不超过新基准 25% 的回归门；人工桌面
  验收通过后才可建立 `v1.0.0-rc.2`。 / All W10 targets pass,
  later runs stay within the 25% regression gate, and `v1.0.0-rc.2` is created
  only after manual desktop acceptance.

## 实施顺序 / Implementation Order

W10.1 必须先闭环，因为它直接解决“未响应”且为后续 Progress 提供可增量刷新
的 UI 边界。W10.2 和 W10.3 分别优化导入/结构与导出。W10.4 在真实分批检查
点已经存在后接入 Progress/Cancel，避免先建空洞任务框架。W10.5 只做资格验证与
RC.2 准备。

W10.1 closes first because it directly addresses the unresponsive-window
symptom and establishes an incrementally refreshable UI boundary for later
progress. W10.2 and W10.3 optimize import/structure and export respectively.
W10.4 adds progress/cancellation only after real batch checkpoints exist,
avoiding an empty task framework. W10.5 performs qualification and RC.2
preparation only.
