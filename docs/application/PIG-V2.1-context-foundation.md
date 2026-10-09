# PIG V2.1 Project Context 基础实施规范 / PIG V2.1 Project Context Foundation Implementation Specification

- 状态：V2.1.4 已实施并通过自动化回归 / Status: V2.1.4 implemented with automated regression passing
- 日期：2026-10-07 / Date: 2026-10-07
- 约束决策：`ADR-010`、`ADR-024`、`ADR-025` / Governing decisions: `ADR-010`, `ADR-024`, `ADR-025`

## 1. 目标与闭环 / Goal and closed loop

V2.1 的唯一目标是在不使用 AI、RAG 或网络的情况下，把用户从 Workspace 选出的关键
文件变成有明确版本、人工说明和主题位置的 Project Context，并能关闭后重新打开。

The sole V2.1 goal is to turn key files selected from the Workspace into a
Project Context with fixed versions, human guidance, and thematic placement,
without AI, RAG, or network access, and to preserve it across reopen.

```text
Open or upgrade V1 Project
  -> Select active terminal Workspace Item
  -> Add to Project Context
  -> Capture immutable Context Revision
  -> Place in zero or more flat Sections
  -> Add human Annotation
  -> Persist, close, reopen, and verify freshness
```

`Unsectioned` 保证零 Placement 的 Active Item 仍可见。Workspace 字节变化只改变
Freshness；只有用户明确执行更新动作才创建新的 Context Revision。

`Unsectioned` keeps an active Item visible when it has no Placement. Workspace
byte changes affect Freshness only; a new Context Revision requires an explicit
user action.

## 2. V2.1 不做什么 / V2.1 non-goals

V2.1 不实现 Context Pack 导出、内容解析、全文检索、OCR、AI、Citation、时间线、思维
导图、平台 Adapter、MCP、Agent 或 Automation。它不替换 Workspace Tree，也不允许
Context 修改 Source、Original 或 Working 字节。

V2.1 does not implement Context Pack export, content extraction, full-text
search, OCR, AI, Citations, timelines, mind maps, platform adapters, MCP, Agents,
or Automation. It does not replace the Workspace Tree and cannot let Context
modify Source, Original, or Working bytes.

## 3. Domain、Flow 与影响 / Domain, flow, and impact

### Domain

新增规划对象为 `ContextSection`、`ContextItem`、`ContextPlacement`、
`ContextContentObject`、`ContextRevision`、`ContextAnnotation` 和 Project 的
`context_revision`。V1 `WorkspaceItem`、`WorkingArtifact`、`SourceNode`、
`OriginalSnapshot` 和 `workspace_revision` 保持权威。

Planned new objects are `ContextSection`, `ContextItem`, `ContextPlacement`,
`ContextContentObject`, `ContextRevision`, `ContextAnnotation`, and Project
`context_revision`. V1 `WorkspaceItem`, `WorkingArtifact`, `SourceNode`,
`OriginalSnapshot`, and `workspace_revision` remain authoritative.

### Flow

用户从 Workspace 发起 Promote；Application 层执行资格、容量和并发预检；Capture
Service 从 Working 或 Source 写入 staging、计算 Hash、发布对象；Repository 在一个
数据库事务中创建/复用 Content Object、创建 Revision、建立或恢复 Item，并推进
`context_revision`；Query Service 返回 Section、Unsectioned、Item Detail 和 Freshness。

The user promotes from Workspace. The Application layer performs eligibility,
capacity, and concurrency preflight. Capture Service stages, hashes, and
publishes bytes from Working or Source. In one database transaction, repositories
create or reuse the Content Object, create the Revision, create or restore the
Item, and advance `context_revision`. Query services return Sections,
Unsectioned, Item Details, and Freshness.

### State

Context Item 为 `ACTIVE/REMOVED`；Section 为 `ACTIVE/REMOVED`；Revision 捕获为
`PENDING/CAPTURING/READY/FAILED/CANCELLED_AT_SAFE_POINT`；Content Object 可用性为
`STAGED/AVAILABLE/ORPHAN_CANDIDATE/MISSING`。Freshness 单独为 `CURRENT`、
`WORKSPACE_UPDATED`、`WORKSPACE_MISSING` 或 `WORKSPACE_UNREADABLE`。

Context Items are `ACTIVE/REMOVED`, Sections are `ACTIVE/REMOVED`, Revision
capture is `PENDING/CAPTURING/READY/FAILED/CANCELLED_AT_SAFE_POINT`, and Content
Object availability is `STAGED/AVAILABLE/ORPHAN_CANDIDATE/MISSING`. Freshness is
separate: `CURRENT`, `WORKSPACE_UPDATED`, `WORKSPACE_MISSING`, or
`WORKSPACE_UNREADABLE`.

### Lineage

最小来源链为 `ContextRevision -> ContextItem -> WorkspaceItem -> SourceNode ->
OriginalSnapshot`。Materialized 路径额外记录 Working Artifact；Virtual 路径记录 Source
Node。Revision 同时引用 Content Object，物理路径不代替来源关系。

The minimum origin chain is `ContextRevision -> ContextItem -> WorkspaceItem ->
SourceNode -> OriginalSnapshot`. A materialized path additionally records its
Working Artifact, while a virtual path records its Source Node. The Revision
also references a Content Object; a physical path never replaces origin
relationships.

### Log

升级、捕获、Section、Placement、Annotation、保留保护、清理预检、容量阻断和并发冲突
均产生结构化业务 Event。完整文件内容、Secret 和异常 Stack Trace 不进入 Event
Metadata；Stack Trace 属于 Debug Log。

Upgrade, capture, Section, Placement, Annotation, retention protection, cleanup
preflight, capacity blocking, and concurrency conflict actions produce structured
business Events. Full file content, secrets, and stack traces do not enter Event
metadata; stack traces remain debug logs.

### Permission and safety

Promote、Section/Placement/Annotation 编辑属于 Project 内写操作；Revision 清理属于破坏
性写操作，必须影响预览和确认。升级先备份。Context Capture 只读 Source/Working，绝不
写回。路径由系统生成，用户文件名不能决定对象路径。

Promotion and Section/Placement/Annotation edits are Project-local writes.
Revision cleanup is destructive and requires impact preview plus confirmation.
Upgrade backs up first. Context capture reads Source or Working and never writes
back. Object paths are system-generated and cannot be controlled by user
filenames.

### Tool, AI, Automation, and UI

首期能力只作为 typed in-process Application Contract，不发布公共 Tool、API 或 MCP。
AI 和 Automation 均不参与。UI 只增加同窗口视图切换和最小 Context 三栏交互。

Initial capabilities remain typed in-process Application Contracts rather than
public Tools, APIs, or MCP. AI and Automation do not participate. UI changes are
limited to same-window view switching and the minimum three-pane Context
interaction.

## 4. 持久化模型草案 / Persistence model draft

以下表边界已由 `0009_project_context_foundation` 实现；其父版本为实施时真实 Head
`0008_workbench_recovery`。

The following table boundaries are implemented by
`0009_project_context_foundation`, whose parent is the verified implementation-
time head `0008_workbench_recovery`.

### `projects`

新增 `context_revision INTEGER NOT NULL DEFAULT 0`，带非负约束。它只由成功提交的
Context 写事务递增。

Add `context_revision INTEGER NOT NULL DEFAULT 0` with a non-negative constraint.
Only a successfully committed Context write transaction increments it.

### `context_settings`

每 Project 一行：`project_id`、`soft_quota_bytes`（默认 10 GiB）、
`minimum_free_bytes`（默认 2 GiB）及时间字段。配置值必须经过边界校验。

One row per Project: `project_id`, `soft_quota_bytes` (default 10 GiB),
`minimum_free_bytes` (default 2 GiB), and timestamps. Values require bounded
validation.

### `context_sections`

字段包括稳定 ID、Project ID、Name、Description、Ordinal、Lifecycle Status 和时间。
V2.1 不存在 `parent_section_id`。Section 名称是显示值，ID 是身份；实现不得用名称
作为外键。

Fields include stable ID, Project ID, name, description, ordinal, lifecycle
status, and timestamps. V2.1 has no `parent_section_id`. A Section name is a
display value and its ID is identity; implementation cannot use names as foreign
keys.

### `context_items`

字段包括 ID、Project ID、唯一 Workspace Item 引用、可选 Title Override、Purpose、
Lifecycle Status、可选 Current Context Revision ID 和时间。一个 Workspace Item 在同一
Project 最多对应一个 Context Item；Removed Item 可恢复，不重复创建。

Fields include ID, Project ID, unique Workspace Item reference, optional title
override, purpose, lifecycle status, optional current Context Revision ID, and
timestamps. One Workspace Item maps to at most one Context Item in a Project;
a removed Item is restored rather than duplicated.

### `context_placements`

显式保存 Item、Section、Ordinal、Lifecycle Status 和时间；同一 Item/Section 对最多一
个有效 Placement。被删除 Section 下的 Placement 继续存在但不生效。

Explicitly stores Item, Section, ordinal, lifecycle status, and timestamps. An
Item/Section pair has at most one effective Placement. Placements under a removed
Section remain durable but are ineffective.

### `context_content_objects`

字段包括 ID、Project ID、SHA-256、Size、Object Key、Availability Status 和时间；
`(project_id, sha256)` 唯一。Object Key 只能是 Project 相对、系统生成的安全路径。

Fields include ID, Project ID, SHA-256, size, object key, availability status,
and timestamps, with unique `(project_id, sha256)`. Object keys are safe,
system-generated Project-relative paths only.

### `context_revisions`

字段包括 ID、Project/Context Item/Content Object 引用、Source Kind、可选 Working
Artifact/Source Node 引用、捕获时 Workspace Revision、Source Observed SHA-256、状态、
保护标记/原因、Actor 和时间。READY 后 Hash、Size、来源和 Content Object 引用不可变。

Fields include ID, Project/Context Item/Content Object references, source kind,
optional Working Artifact/Source Node references, captured Workspace revision,
source-observed SHA-256, state, protection flag/reason, actor, and timestamps.
After READY, hash, size, origin, and Content Object reference are immutable.

### `context_annotations`

字段包括 ID、Project/Context Item 引用、可选 Revision 引用、Kind、Body、Author 和时间。
V2.1 只支持 Item 级人工说明；AI 输出不能写入此表。

Fields include ID, Project/Context Item references, optional Revision reference,
kind, body, author, and timestamps. V2.1 supports human Item-level guidance only;
AI output cannot enter this table.

## 5. Application Contracts / Application contracts

V2.1 规划以下 typed Action/Query；名称可在实现前进行局部调整，但语义和安全边界不得
退化：

V2.1 plans the following typed Actions and Queries. Names may receive local
refinement before implementation, but semantics and safety boundaries cannot be
weakened:

- `preflight_project_context_upgrade`
- `upgrade_project_to_v2_context`
- `promote_workspace_item_to_context`
- `advance_context_revision`
- `remove_context_item` / `restore_context_item`
- `create_context_section` / `rename_context_section`
- `remove_context_section` / `restore_context_section`
- `place_context_item` / `remove_context_placement` / `reorder_context_placement`
- `upsert_context_annotation`
- `protect_context_revision` / `unprotect_context_revision`
- `preview_context_revision_cleanup`
- `execute_context_revision_cleanup`
- `get_project_context`
- `get_context_item_details`
- `get_context_freshness`

所有写 Action 接收 `project_id`、Actor、Correlation ID 和预期
`context_revision`。涉及捕获的 Action 还接收预期 Workspace 状态。结果使用明确的
Status、Error Code、影响对象 ID 和最新并发版本，不返回任意 Dict。

Every write Action accepts `project_id`, actor, correlation ID, and expected
`context_revision`. Capture Actions additionally accept expected Workspace state.
Results use explicit status, error code, affected object IDs, and latest
concurrency revisions rather than arbitrary dictionaries.

## 6. 捕获事务与失败恢复 / Capture transaction and failure recovery

1. 校验 Project 模型、Item 资格、预期 Workspace/Context Revision；
2. 刷新 Materialized Working 状态，或解析 Virtual Source materialization recipe；
3. 估算所需空间并应用 10 GiB 软提醒与 2 GiB 最低剩余空间门；
4. 写入 operation-scoped staging，同时流式计算 SHA-256 和 Size；
5. 再次校验捕获来源未在处理中发生变化；
6. 若对象已存在则验证并复用，否则原子发布到 Content Object Path；
7. 在单一数据库事务中创建/复用对象行、创建 READY Revision、推进 Item Current
   Revision、应用默认保留保护并递增 `context_revision`；
8. 提交后发出 Event 并安全清理 staging；
9. 若数据库提交失败，已发布但无引用对象标记为 Orphan Candidate，由恢复扫描处理，
   不把它显示为有效 Revision。

1. Validate Project model, Item eligibility, and expected Workspace/Context revisions.
2. Refresh materialized Working state or resolve the virtual Source materialization recipe.
3. Estimate required space and apply the 10 GiB soft warning and 2 GiB free-space gate.
4. Stream into operation-scoped staging while computing SHA-256 and size.
5. Revalidate that the capture source did not change during processing.
6. Verify and reuse an existing object, or atomically publish a new one.
7. In one database transaction, create/reuse the object row, create the READY
   Revision, advance the Item current pointer, apply default retention protection,
   and increment `context_revision`.
8. Emit Events after commit and safely clean staging.
9. If database commit fails, treat an already-published unreferenced object as an
   Orphan Candidate for recovery scanning and never display it as a valid Revision.

取消只允许在 staging copy/hash 等安全点。完成数据库提交后不得把已提交 Revision 标记
为取消；用户若不再需要，应通过显式 Remove 或未来 Cleanup 流程处理。

Cancellation is allowed only at safe points such as staging copy/hash. After
database commit, a committed Revision cannot be relabeled as cancelled; explicit
Remove or a future Cleanup flow handles later intent.

## 7. 升级流程 / Upgrade flow

```text
Detect V1 model
  -> Read-only preflight and explain impact
  -> User confirms
  -> Check no active Project write
  -> SQLite integrity check
  -> Create timestamped pre-V2 database backup
  -> Verify backup integrity
  -> Run forward Alembic migration in controlled mode
  -> Validate V1 row counts, key relationships, and model invariants
  -> Set new model version
  -> Reopen with V2.1 repositories
```

备份位于 Project 内受控备份目录，文件名带 UTC Timestamp 且不覆盖旧备份。失败时关闭
写入入口、保留原数据库和备份、记录 `ProjectContextUpgradeFailed`；恢复必须显式重试
或从已验证备份恢复，不能继续半升级运行。

The backup uses a managed Project backup directory, a UTC timestamped filename,
and never overwrites an earlier backup. Failure disables write entry points,
retains the database and backup, and records `ProjectContextUpgradeFailed`.
Recovery requires explicit retry or restoration from a verified backup; PIG
cannot continue with a partial upgrade.

## 8. 最小 UI / Minimum UI

```text
[Workspace] [Project Context]

Project Context
┌──────────────┬────────────────────────┬──────────────────────┐
│ Sections     │ Context Items          │ Item Details         │
│ - Section A  │ title / freshness      │ origin / revision    │
│ - Section B  │ purpose / status       │ annotation / actions │
│ - Unsectioned│                        │ placements           │
└──────────────┴────────────────────────┴──────────────────────┘
```

Workspace 右键菜单的 `Add to Project Context` 先展示捕获来源和容量预检；成功后切换不是
强制行为。Item Details 提供更新 Revision、说明和 Placement 操作。长时 Hash/Copy 必须
在受控后台任务运行，UI 保持响应并允许安全点取消。

The Workspace context-menu action `Add to Project Context` first shows capture
source and capacity preflight; successful promotion does not force a view switch.
Item Details provides Revision update, guidance, and Placement actions. Long
hash/copy work runs as bounded background work, keeping UI responsive and
allowing safe-point cancellation.

## 9. 结构化事件 / Structured events

V2.1 至少记录：

V2.1 records at least:

- `ProjectContextUpgradeRequested/Started/Completed/Failed`
- `ContextCapturePreflighted/Started/Completed/Failed/Cancelled`
- `ContextCaptureBlockedByCapacity`
- `ContextContentObjectReused/Published/OrphanDetected`
- `ContextItemPromoted/Removed/Restored`
- `ContextRevisionAdvanced/Protected/Unprotected`
- `ContextRevisionCleanupCompleted/Failed`
- `ContextSectionCreated/Renamed/Removed/Restored/Reordered`
- `ContextPlacementCreated/Removed/Reordered`
- `ContextAnnotationCreated/Updated`
- `ContextBecameOutdated`
- `ContextWriteConflict` / `WorkspaceChangedDuringCapture`
- `ContextCleanupPreviewed/Confirmed`

Event Metadata 只包含稳定 ID、状态、大小、Hash 摘要、来源类型、错误码、Actor、UTC
Timestamp 和 Correlation ID 等安全字段。

Event metadata contains only safe fields such as stable IDs, state, size, hash
summary, source type, error code, actor, UTC timestamp, and correlation ID.

## 10. 分阶段实施顺序 / Staged implementation order

进入实现后仍需逐段完成和验收，不能一次性越过：

After implementation is separately authorized, work still proceeds and closes
in these stages rather than skipping ahead:

1. **V2.1.1 Upgrade + Schema**：备份、Migration、Mapping、Repository、
   `context_revision`；无 UI。
2. **V2.1.2 Capture Core**：Content Object、Working/Virtual Capture、Hash、容量门、
   原子发布和恢复扫描。
3. **V2.1.3 Context Actions**：Item、Section、Placement、Annotation、保留保护、
   经预览确认的清理、Freshness 和并发冲突。
4. **V2.1.4 Minimum UI**：双视图、三栏 Context、Workspace Promote、后台进度和错误。
5. **V2.1.5 Acceptance**：大文件、虚拟 Container Child、冲突、容量阻断、取消、
   重启和回归验收；本轮旧 V1 数据库适配按产品负责人要求排除。

1. **V2.1.1 Upgrade + Schema**: backup, migration, mappings, repositories, and
   `context_revision`, with no UI.
2. **V2.1.2 Capture Core**: Content Objects, Working/virtual capture, hashes,
   capacity gates, atomic publication, and recovery scanning.
3. **V2.1.3 Context Actions**: Items, Sections, Placements, Annotations, retention
   protection, preview-confirmed cleanup, Freshness, and concurrency conflicts.
4. **V2.1.4 Minimum UI**: dual views, three-pane Context, Workspace promotion,
   background progress, and errors.
5. **V2.1.5 Acceptance**: large files, virtual container children, conflicts,
   capacity blocking, cancellation, reopen, and regression acceptance; old V1
   database adaptation is excluded from this run at the product owner's request.

## 11. 测试与验收 / Tests and acceptance

### 最小测试矩阵 / Minimum test matrix

以下 Migration 项是 D115-A 的长期验收要求，不属于本轮 V2.1.5 签收范围；
本轮具体范围以 `PIG-V2.1.5-acceptance.md` 为准。

The Migration item below is a longer-term D115-A acceptance requirement, not
part of this V2.1.5 sign-off run. The specific run scope is defined in
`PIG-V2.1.5-acceptance.md`.

- Migration：V1 真实 Fixture 前向升级、备份校验、失败不更新模型版本、重复打开幂等；
- Storage：相同字节去重、不同 Project 不共享、损坏对象拒绝、原子发布、Orphan 恢复；
- Capture：Working 当前字节、Virtual Source、缺失/不可读 Working、处理中 Workspace 改变；
- Quota：10 GiB 警告、2 GiB 预测阻断、配置边界、无自动清理；
- Domain：多 Placement、Section 软删除/恢复、虚拟 Unsectioned、Item 移除/恢复；
- Revision：当前+上一版本、引用/手动保护、Cleanup Candidate 计算、陈旧预览拒绝和
  确认后安全清理；
- Concurrency：Workspace 与 Context Revision 分离、陈旧写冲突、并发 Promote 幂等；
- UI：滚动和切换心跳、后台捕获、取消安全点、错误可见、重启状态一致；
- Regression：V1 Import/Open/Edit/Refresh/Search/Export 和 Original 不变。

- Migration: forward-upgrade a realistic V1 fixture, verify backup, preserve model
  version on failure, and make repeated open idempotent.
- Storage: deduplicate equal bytes, isolate Projects, reject corrupt objects,
  atomically publish, and recover Orphans.
- Capture: current Working bytes, virtual Source, missing/unreadable Working, and
  Workspace mutation during capture.
- Quota: 10 GiB warning, projected 2 GiB block, configuration bounds, and no
  automatic cleanup.
- Domain: multiple Placements, Section soft delete/restore, virtual Unsectioned,
  and Item remove/restore.
- Revision: current plus previous, reference/manual protection, Cleanup Candidate
  calculation, stale-preview rejection, and safe confirmed cleanup.
- Concurrency: separate Workspace/Context revisions, stale-write conflicts, and
  idempotent concurrent promotion.
- UI: scrolling and switch heartbeat, background capture, safe cancellation,
  visible errors, and reopen consistency.
- Regression: V1 import/open/edit/refresh/search/export and Original immutability.

### 验收条件 / Acceptance criteria

1. D115-A 的当前 V1 Project 升级需单独验收；本轮不据此宣称旧库兼容性；
2. Materialized 与 Virtual Item 都能成为 Context，且捕获期间 UI 不冻结；
3. 相同字节在同一 Project 去重，Revision 身份和来源关系完整；
4. Item 可以出现在多个扁平 Section；Section 删除后 Item 在 `Unsectioned` 可见，恢复
   后 Placement 恢复；
5. 人工说明、Current Revision、Freshness 和 Placement 在重启后保持；
6. Workspace 改动只产生 `WORKSPACE_UPDATED`，不会自动覆盖 Context；
7. 默认保留当前和上一 Revision；被引用或保护 Revision 不成为清理候选；
8. 清理只能删除预览中仍符合资格且经用户确认的 Revision；引用变化会使旧预览失效；
9. 磁盘和并发冲突以结构化错误安全失败，不产生半发布 Revision；
10. Original、Source、Workspace 结构和 Working 字节不被 Context Action 修改；
11. 全部能力离线运行，没有 AI、RAG 或新平台依赖。

1. D115-A upgrade of a current V1 Project requires separate acceptance; this
   run does not claim compatibility with old databases.
2. Materialized and virtual Items can enter Context without freezing the UI.
3. Equal bytes deduplicate inside one Project while Revision identity and origin
   relationships remain complete.
4. An Item can appear in multiple flat Sections; after Section removal it remains
   visible under `Unsectioned`, and restoring the Section restores Placements.
5. Human guidance, current Revision, Freshness, and Placements survive reopen.
6. Workspace changes produce `WORKSPACE_UPDATED` and never overwrite Context.
7. Current and previous Revisions are retained by default, while referenced or
   protected Revisions never become cleanup candidates.
8. Cleanup deletes only Revisions that remain eligible from a user-confirmed
   preview; changed references invalidate a stale preview.
9. Disk and concurrency conflicts fail safely with structured errors and no
   partial Revision publication.
10. Context Actions do not modify Original, Source, Workspace structure, or
   Working bytes.
11. Everything runs offline with no AI, RAG, or new platform dependency.

## 12. 当前授权门 / Current authorization gate

V2.1.4 Minimum UI 已按 `PIG-V2.1.4-minimum-ui-plan.md` 实施并通过自动化回归。
V2.1.5 Acceptance 已通过合成数据自动测试，用户已确认源码桌面人工验收通过；
不得未经单独授权进入 V2.2。

V2.1.4 Minimum UI is implemented according to
`PIG-V2.1.4-minimum-ui-plan.md` and has passed automated regression. V2.1.5
Acceptance passed synthetic automated tests and user-reported source-desktop
manual acceptance; V2.2 must not begin without separate authorization.
