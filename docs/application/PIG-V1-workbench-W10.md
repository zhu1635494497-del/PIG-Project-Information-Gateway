# PIG V1 Workbench W10 性能与响应性稳定 / Performance and Responsiveness Stabilization

- 状态：W10.1–W10.4 已完成；W10.5 自动资格 Gate 与源码桌面滚动修复复验已通过，等待最终打包桌面人工验收 / Status: W10.1-W10.4 complete; W10.5 automated qualification gates and source-desktop re-acceptance of the scrolling fix pass; final-package manual desktop acceptance remains pending
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

### W10.1 实施证据 / W10.1 Implementation Evidence

- 完成日期：2026-09-26。 / Completed: 2026-09-26.
- Workspace Tree 从每个 Item 多次 Repository 查询改为固定三条 SQL：Project、轻量
  Placement Graph、Set-based Joined Projection；路径和有效状态在线性时间内计算。 /
  Workspace Tree changed from repeated per-item repository calls to three fixed
  SQL statements: Project, a lightweight placement graph, and a set-based joined
  projection. Paths and effective state are resolved in linear time.
- Search 使用固定四条 SQL：Project、Placement Graph、数据库 Count 和数据库 Page；
  Format、Content Status、Lifecycle 和 Query Candidate 在数据库边界过滤。 / Search
  uses four fixed SQL statements: Project, placement graph, database count, and
  database page. Format, content status, lifecycle, and query candidates are
  filtered at the database boundary.
- UI 已迁移到 `QTreeView + QAbstractItemModel`；Qt 只为请求的行创建 `QModelIndex`，
  不再全量构造 `QTreeWidgetItem`。 / The UI now uses
  `QTreeView + QAbstractItemModel`; Qt creates `QModelIndex` values only for
  requested rows and no longer builds every `QTreeWidgetItem`.
- Activity Record 改为 typed Recent Events Query，默认只读取最近 300 条，不再通过
  完整 Project Overview 加载全部 Event。 / Activity Record now uses a typed
  recent-events query, reading only the latest 300 by default instead of loading
  all Events through the complete Project Overview.
- 同参考主机三轮中位数：10,000 Item Tree `1.121s`，Search `0.290s`；旧基线分别为
  `5.734s` 与 `5.775s`。 / Three-run medians on the reference host are `1.121s`
  for a 10,000-item Tree and `0.290s` for Search, versus the old `5.734s` and
  `5.775s` baselines.
- 10,000 Item Qt Model Reset 为 `0.010s`，Reset 后未预建任何 Item Index，单个请求
  Index 约 `0.00002s`。 / Resetting the 10,000-item Qt model takes `0.010s`;
  no item indexes are prebuilt after reset, and one requested index takes about
  `0.00002s`.
- 2026-09-27 源码桌面人工验收发现 Workspace 点击与滚轮仍有可感知停顿。根因位于
  Qt 展示热路径：行重绘会重复生成图标和显示值，Sibling Row 查找为线性扫描，且
  三个辅助列使用全内容自动测宽。修复后显示值与图标按 Model 生命周期缓存，Row
  查找使用预计算映射，辅助列改为有界可调宽度，Tree 使用像素级滚动。新增 10,000
  行、201 个滚动步的 UI Gate，要求平均每步低于 `25 ms` 且不得全量绘制图标；当前
  参考主机通过。 / Source-desktop acceptance on 2026-09-27 found perceptible
  stalls when clicking and scrolling the Workspace. The cause was in the Qt
  presentation hot path: row repaints regenerated icons and display values,
  sibling-row lookup was linear, and three secondary columns measured all
  content for width. Display values and icons are now cached for the model
  lifetime, row lookup uses a precomputed map, secondary columns use bounded
  user-adjustable widths, and the Tree scrolls per pixel. A new 10,000-row,
  201-step UI gate requires less than `25 ms` per step on average without eager
  icon painting; it passes on the reference host.
- 全量回归：`149 passed, 95 skipped`；Skip 属于 ADR-010 后的历史 Contract 或主机
  Symlink 限制。 / Full regression: `149 passed, 95 skipped`; skips are historical
  contracts superseded by ADR-010 or host symlink restrictions.
- 本阶段不创建 `0009`：现有索引已达到目标，缺少新增索引的 Query Plan 证据。 /
  W10.1 does not create `0009`: current indexes meet the targets and no query-plan
  evidence justifies another index.

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

### W10.2 实施证据 / W10.2 Implementation Evidence

- 完成日期：2026-09-26。 / Completed: 2026-09-26.
- Import Repository 新增 Original Artifact 与 Snapshot Entry 的有界批量写入；完整批次
  在写入前统一验证 Snapshot、Parent 与 Artifact 边界。 / Import repositories now
  provide bounded bulk writes for Original Artifacts and Snapshot Entries; each
  complete batch validates Snapshot, parent, and Artifact boundaries before
  insertion.
- Structure Application 先形成 ID Map 与完整持久化计划，再按 Node/Relationship/Lineage、
  Locator、Metadata、Attempt、Workspace、Event 的依赖顺序写入。 / The Structure
  Application first builds an ID map and complete persistence plan, then writes
  Node/Relationship/Lineage, Locator, Metadata, Attempt, Workspace, and Event
  records in dependency order.
- 新 Node 不再执行逐节点 Parent/Lineage 查询和三次中间状态更新；Lineage Closure 在内存
  中按深度生成，数据库仍只保存相同的最终状态和历史 Event。 / New Nodes no longer
  perform per-node parent/lineage queries or three intermediate status updates;
  lineage closure is generated by depth in memory while the database retains the
  same final states and historical Events.
- 所有批量写入仍位于原有单 Source Unit of Work；任何后段失败会回滚 Job、Root 状态、
  Node、Relationship、Lineage、Workspace 与 Event。顶层 Sibling 失败隔离策略不变。 /
  All bulk writes remain inside the original per-Source unit of work; a late
  failure rolls back the Job, root state, Nodes, Relationships, Lineage,
  Workspace, and Events. Top-level sibling failure isolation is unchanged.
- 同参考主机三轮中位数：2,000 文件 Snapshot `7.243s`，旧基线 `10.904s`；10,000-entry
  ZIP Inspect `17.932s`，旧基线 `108.339s`。 / Three-run medians on the
  reference host are `7.243s` for a 2,000-file Snapshot versus the old `10.904s`,
  and `17.932s` for a 10,000-entry ZIP inspection versus the old `108.339s`.
- 两项正式测量的最大 Peak RSS 为 `213,319,680` bytes（约 `203.4 MiB`），低于
  `300 MiB` Gate。 / Maximum Peak RSS across both formal measurements is
  `213,319,680` bytes (about `203.4 MiB`), below the `300 MiB` gate.
- 新增批量/单条等价、Snapshot 整事务回滚和 Structure 后段故障注入回滚测试；现有
  Duplicate、Traversal、Limit、Encrypted、Sibling Continuation 回归保持通过。 /
  Added bulk/single equivalence, whole-Snapshot rollback, and injected late
  Structure-failure rollback tests; existing duplicate, traversal, limit,
  encrypted, and sibling-continuation regressions remain green.
- 全量回归：`153 passed, 95 skipped`，另有一个预期 Duplicate ZIP Warning。 / Full
  regression: `153 passed, 95 skipped`, with one expected duplicate-ZIP warning.
- 本阶段不增加 Migration、UI 页面、Tool、AI、Automation 或异步任务系统。 / This
  phase adds no migration, UI page, Tool, AI, Automation, or asynchronous task
  system.

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

### W10.3 实施证据 / W10.3 Implementation Evidence

- 完成日期：2026-09-26。 / Completed: 2026-09-26.
- Export Application 使用一次 set-based Workspace Read Projection 和两条有界
  Original Artifact 查询完成选择、有效状态、子树、路径、Working 与 Source 映射；
  不再为每个 Item 重复打开读事务。 / The Export Application now uses one
  set-based Workspace Read Projection and two bounded Original Artifact queries
  for selection, effective state, subtree, path, Working, and Source mapping; it
  no longer opens repeated read transactions for every Item.
- 未编辑且可直接映射到 Project Original Snapshot 的 Virtual 文件从不可变 Original
  流式导出，不再为了交付而创建 Working File 和 Working Version；Archive/Email 内部
  成员仍使用既有安全 Materialization Recipe。 / Unedited Virtual files that map
  directly to the Project Original Snapshot are streamed from immutable
  Originals without creating a Working File and Working Version merely for
  delivery. Archive and email members continue to use the existing safe
  materialization recipe.
- Working File 的持久 Checkpoint 与当前 size/mtime 一致时跳过导出前完整 Hash；最终
  复制或 ZIP 写入仍在单次流式读取中计算 SHA-256，并同时验证前后文件事实，因此
  相同 size/mtime 的内容篡改仍会失败。 / A Working File skips the pre-export
  full hash when its persisted checkpoint matches current size/mtime. The final
  copy or ZIP write still computes SHA-256 in the single streaming read and
  validates before/after file facts, so content tampering with unchanged
  size/mtime still fails.
- 普通目录、ZIP 和单文件输出继续使用受控相对路径、Collision 检查、显式 Replace
  Confirmation、暂存输出及失败清理；单文件保留发布前 `fsync`，目录不再为每个小文件
  单独 `fsync`。 / Directory, ZIP, and single-file outputs retain controlled
  relative paths, collision checks, explicit replacement confirmation, staged
  output, and failure cleanup. Single-file publication keeps its pre-publish
  `fsync`, while directory export no longer performs one `fsync` per small file.
- 同参考主机三轮中位数：500 文件 Folder Export `1.655s`，旧基线 `71.074s`；500 文件
  ZIP Export `1.225s`，旧基线 `21.205s`。两项最大 Peak RSS 为 `111,833,088`
  bytes（约 `106.7 MiB`）。 / Three-run medians on the reference host are
  `1.655s` for a 500-file Folder Export versus the old `71.074s`, and `1.225s`
  for a 500-file ZIP Export versus the old `21.205s`. Maximum Peak RSS across
  both measurements is `111,833,088` bytes (about `106.7 MiB`).
- 新增虚拟 Original 直出、Working 快速路径和相同 stat 内容变化拒绝测试；既有
  Modified/Missing/Unreadable、Collision、Empty Folder、Replace Confirmation 与失败
  原子清理回归保持通过。 / Added tests for direct Virtual-to-Original export,
  the Working fast path, and rejection of same-stat content changes; existing
  Modified/Missing/Unreadable, collision, empty-folder, replacement-confirmation,
  and atomic failure-cleanup regressions remain green.
- 全量回归：`158 passed, 95 skipped`，另有一个预期 Duplicate ZIP Warning。 / Full
  regression: `158 passed, 95 skipped`, with one expected duplicate-ZIP warning.
- 本阶段不增加 Migration、UI 页面、Tool、AI、Automation 或 Progress/Cancel；Typed
  Progress、协作取消和 Resource Preflight 仍属于 W10.4。 / This phase adds no
  migration, UI page, Tool, AI, Automation, or Progress/Cancel. Typed progress,
  cooperative cancellation, and resource preflight remain W10.4 work.

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

### W10.4 实施证据 / W10.4 Implementation Evidence

- 完成日期：2026-09-26。 / Completed: 2026-09-26.
- 新增进程内 typed Operation Control，统一提供 Stage、Count、Bytes、Current Item、
  Warning、Cancellable 与 Cancellation Requested；Progress 只存在于当前 Action，
  不增加业务表或持久任务实体。 / Added an in-process typed Operation Control that
  exposes stage, count, bytes, current item, warning, cancellability, and
  cancellation-requested state. Progress exists only for the current action and
  adds no business table or persistent-task entity.
- Import、Structure Inspection 与 Export 在文件、Container、批次和数据块边界检查
  Cancellation Token；进入原子发布或数据库提交后切换为不可取消，让当前原子步骤
  安全完成。 / Import, structure inspection, and export check the cancellation
  token at file, Container, batch, and data-block boundaries. Once atomic
  publication or database commit begins, the action becomes non-cancellable so
  that the current atomic step finishes safely.
- Import 预检在创建 Session/Snapshot 前计算条目数、总字节、单文件限制和 Project
  磁盘余量；Export 在创建暂存输出前检查目标卷磁盘余量。超限拒绝和取消结果进入
  既有结构化 Event，精确失败原因保存在 Event Details；未新增 Migration。 /
  Import preflight computes entry count, total bytes, per-file limits, and
  Project free space before creating a Session/Snapshot. Export checks target
  volume free space before staging output. Limit rejections and cancellations
  use existing structured Events, with the exact failure reason in Event
  Details; no migration was added.
- Desktop 保持单后台 Action Busy Policy，并新增确定/不确定 Progress、当前项目提示和
  Cancel 按钮；自动 UI 测试确认首次阶段反馈低于 `500 ms`，取消期间事件循环仍可处理
  重绘与输入。 / The desktop retains the single-background-action busy policy
  and adds determinate/indeterminate progress, current-item text, and a Cancel
  button. Automated UI tests confirm initial stage feedback below `500 ms` and
  a responsive event loop while cancellation is pending.
- 故障注入覆盖 Snapshot Copy 取消、Structure Planning 取消、Export Write 取消、磁盘
  不足和 Atomic Publish 期间延迟取消；验证 `INTERRUPTED` 状态、暂存清理、无半棵
  Workspace Tree、完成中的原子发布和 Project 重开。 / Fault injection covers
  cancellation during Snapshot copy, structure planning, and export write,
  insufficient disk, and deferred cancellation during atomic publication. It
  verifies `INTERRUPTED` state, staging cleanup, absence of partial Workspace
  trees, completion of in-flight atomic publication, and clean Project reopen.
- 当前参考主机单轮代表性实测：80 MiB 单文件完整导入与建树 `0.928s`，首次 Progress
  `0.083s`；2,000 文件、78.125 MiB 文件夹完整导入与建树 `48.394s`，首次 Progress
  `0.028s`，Peak RSS `128,819,200` bytes（约 `122.9 MiB`）。后者证明交互反馈和内存
  边界达标，但端到端多文件吞吐仍作为 W10.5 的明确收口观察项，不宣称为跨设备
  SLA。 / One-run representative measurements on the reference host: complete
  import and tree construction for one 80 MiB file took `0.928s`, with first
  progress at `0.083s`; a 2,000-file, 78.125 MiB folder took `48.394s`, with
  first progress at `0.028s` and Peak RSS of `128,819,200` bytes (about
  `122.9 MiB`). The latter demonstrates acceptable interaction feedback and
  memory bounds, while end-to-end many-file throughput remains an explicit
  W10.5 closure observation rather than a cross-device SLA claim.
- 全量回归：`167 passed, 95 skipped`，另有一个预期 Duplicate ZIP Warning。 /
  Full regression: `167 passed, 95 skipped`, with one expected duplicate-ZIP
  warning.
- 本阶段不增加 Tool、Workflow、Automation、AI、分布式 Worker、持久 Pause/Resume 或
  新 UI 页面。 / This phase adds no Tool, Workflow, Automation, AI,
  distributed worker, persistent pause/resume, or new UI page.

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

### W10.5 实施与资格证据 / W10.5 Implementation and Qualification Evidence

- 正式基准工具现在执行固定 Fixture、三轮中位数、Peak RSS、SQLite 最大尺寸、首次
  Progress、绝对 Gate、RC.1 对比和 Query Plan 证据。基准证据保存于
  `release/performance-baseline-v1.0.0-rc.2.json`。 / The formal benchmark now
  executes fixed fixtures, three-run medians, Peak RSS, maximum SQLite size,
  first progress, absolute gates, the RC.1 comparison, and query-plan evidence.
  The benchmark evidence is stored in
  `release/performance-baseline-v1.0.0-rc.2.json`.
- Snapshot Folder Capture 复用 Preflight 产生的一次性 typed Plan，复制时仍逐项重新
  检查类型和稳定性，完成后重新核对目录成员；大量小文件不再重复遍历目录或对每个
  可从外部输入恢复的 Staging 文件单独 `fsync`。原子发布、SHA-256、资源限制、
  Link 拒绝和输入变化检测保持有效。 / Snapshot Folder Capture reuses the
  one-use typed plan produced by preflight, rechecks type and stability for each
  copied member, and verifies final directory membership. Large small-file sets
  no longer repeat directory discovery or individually `fsync` every staging
  file that remains recoverable from the external input. Atomic publication,
  SHA-256, resource limits, link rejection, and input-change detection remain
  enforced.
- Working 版本旋转对不可变 Current Checkpoint 优先使用同卷硬链接，随后完整重算
  SHA-256 并验证文件身份；不支持硬链接时自动回退到原有 Copy+SHA 路径。可编辑
  Working 文件从不与版本文件共享硬链接。Processing 与 Open/Refresh 的默认有界
  I/O 块调整为 `4 MiB`，不减少 Hash 或稳定性检查。 / Working-version rotation
  prefers a same-volume hard link for the immutable current checkpoint and then
  fully recomputes SHA-256 and verifies file identity. Filesystems without hard
  links automatically fall back to the original copy-plus-hash path. The
  editable Working file never shares a hard link with a version file. Default
  bounded I/O blocks for Processing and Open/Refresh are now `4 MiB`, without
  removing hash or stability checks.
- PyInstaller 规范排除由开发机 `PATH` 误带入的版本化 ICU DLL，防止其遮蔽 Windows
  系统 ICU 并导致 `PySide6.QtCore` 启动失败。最终资格包的 ICU 冲突检查、Runtime
  Smoke 和 Packaged Flow 均通过。 / The PyInstaller specification excludes
  versioned ICU DLLs accidentally exposed by the developer `PATH`, preventing
  them from shadowing Windows system ICU and breaking `PySide6.QtCore` startup.
  The final qualification package passed the ICU collision check, runtime smoke,
  and packaged flow.

| 指标 / Metric | 三轮中位数 / Three-run median | Gate / Result |
| --- | ---: | --- |
| 10,000 Workspace Tree | `0.895s` | `≤1.5s`，通过 / pass |
| 10,000 Workspace Search | `0.225s` | `≤0.75s`，通过 / pass |
| 2,000-file Snapshot | `5.245s` | `≤8.5s`，通过 / pass |
| 10,000-entry ZIP Inspect | `18.472s` | `≤35s`，通过 / pass |
| 64 MiB Materialize | `0.881s` | RC.1 25% 相对门通过 / RC.1 25% relative gate passed |
| 64 MiB Refresh | `0.811s` | RC.1 25% 相对门通过 / RC.1 25% relative gate passed |
| 500-file Folder Export | `2.566s` | `≤25s`，通过 / pass |
| 500-file ZIP Export | `2.419s` | `≤13s`，通过 / pass |
| 80 MiB Single-file Add | `0.960s`；首次 Progress `0.031s` | Progress Gate 通过 / pass |
| 2,000-file / 78.125 MiB Add | `45.910s`；首次 Progress `0.029s` | Progress Gate 通过；记录吞吐 / pass; throughput recorded |

- 最大 Peak RSS 为约 `214.1 MiB`，低于 `300 MiB`；SQLite 最大尺寸为
  `87,863,296` bytes。所有绝对 Gate 与 RC.1 25% 相对门均通过。 / Maximum Peak RSS is about
  `214.1 MiB`, below `300 MiB`; maximum SQLite size is `87,863,296` bytes. All
  absolute and RC.1 comparison gates pass.
- Query Plan 使用现有 `ix_workspace_items_origin`、
  `ix_processing_events_project_time` 及相关唯一索引；没有证据支持 `0009`，因此不创建
  Migration。 / Query plans use the existing `ix_workspace_items_origin`,
  `ix_processing_events_project_time`, and related unique indexes. No evidence
  justifies `0009`, so no migration is created.
- 滚动响应性修复后的最终全量回归为 `176 passed, 95 skipped`，另有一个预期 Duplicate ZIP Warning；
  Migration Head 为 `0008_workbench_recovery`，专项 Migration 测试 `4 passed`。 /
  Final full regression after the scrolling-responsiveness fix is `176 passed,
  95 skipped`, with one expected duplicate-ZIP warning. Migration head is
  `0008_workbench_recovery`, and the focused migration suite reports `4 passed`.
- W10.5 自动性能、Migration、测试与 Package Gate 已通过；2026-09-27 源码桌面滚动
  修复复验已由产品负责人确认通过。重新构建包的 ICU 冲突检查、Runtime Smoke 与
  Packaged Flow 已通过，但最终打包桌面仍需人工操作验收。版本保持 `1.0.0rc1`，最终
  打包桌面验收前不得创建 `v1.0.0-rc.2` Tag 或 Release。 / W10.5 automated
  performance, migration, test, and package gates pass. On 2026-09-27, the
  product owner confirmed that source-desktop re-acceptance of the scrolling
  fix passed. The rebuilt package passes the ICU collision check, runtime smoke,
  and packaged flow, but still requires hands-on final-package desktop
  acceptance. Version remains `1.0.0rc1`; no `v1.0.0-rc.2` tag or release may be
  created before final-package desktop acceptance.

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
