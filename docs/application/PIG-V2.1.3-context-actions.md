# PIG V2.1.3 Context Actions 实施记录 / PIG V2.1.3 Context Actions Implementation Record

- 状态：已完成 / Status: Complete
- 日期：2026-10-08 / Date: 2026-10-08
- Migration：`0011_context_actions` / Migration: `0011_context_actions`
- 约束决策：`ADR-024`、`ADR-025` / Governing decisions: `ADR-024`, `ADR-025`

## 1. 实施范围 / Implemented scope

本阶段完成 Workspace 到 Project Context 的确定性 Application 闭环：Promote、
Revision Advance、Item 生命周期、扁平 Section、显式多 Placement、Item Guidance、
Freshness Query、Revision 人工保护，以及预览确认式保留清理。当前没有 UI、正文提取、
AI/RAG、MCP、平台适配或自动化规则。

This stage completes the deterministic Application loop from Workspace to Project
Context: promotion, Revision advancement, Item lifecycle, flat Sections, explicit
multiple Placements, Item guidance, freshness queries, manual Revision protection,
and preview-confirmed retention cleanup. It adds no UI, content extraction,
AI/RAG, MCP, platform adapter, or automation rule.

## 2. Domain、Flow 与关系 / Domain, flow, and relationships

### Domain

本阶段操作 `ContextItem`、`ContextRevision`、`ContextContentObject`、
`ContextSection`、`ContextPlacement`、`ContextAnnotation`、`WorkspaceItem` 和
`Project.context_revision`。Item 与 Workspace Item 一对一；Item 与 Section 通过
Placement 形成显式多对多关系；Annotation 是 Item 级 Guidance，可选择固定到某个
Revision。

This stage operates on `ContextItem`, `ContextRevision`, `ContextContentObject`,
`ContextSection`, `ContextPlacement`, `ContextAnnotation`, `WorkspaceItem`, and
`Project.context_revision`. An Item maps one-to-one to a Workspace Item; Items
and Sections form an explicit many-to-many relation through Placements; an
Annotation is Item-level guidance that may optionally pin one Revision.

### Promote and revision flow

```text
Active source-backed terminal Workspace Item
  -> validate workspace_revision and context_revision
  -> create or restore Context Item
  -> invoke V2.1.2 Capture Core
  -> capture Working or virtual Source bytes
  -> publish/reuse immutable Content Object
  -> create READY Context Revision
  -> set Item current Revision
  -> advance Project context_revision
  -> append structured Events
```

重复 Promote 已有 Current Revision 的 Active Item 是幂等操作。首次捕获失败时保留
Item 和 FAILED Revision 作为错误事实，`context_revision` 不推进，用户可重试。

Repeated promotion of an active Item that already has a current Revision is
idempotent. If the first capture fails, the Item and FAILED Revision remain as
error facts, `context_revision` does not advance, and the user may retry.

### Organization and freshness

Section 是扁平有序对象，删除与恢复均为软生命周期变化。Placement 是独立关系；同一
Item 可出现在多个 Section。没有有效 Placement 的 Active Item 由 Query 投影到虚拟
`Unsectioned`，不另建数据库行。Freshness 通过当前 READY Revision 与 Working 状态和
SHA-256 确定性比较，返回 `CURRENT`、`WORKSPACE_UPDATED`、`WORKSPACE_MISSING` 或
`WORKSPACE_UNREADABLE`，查询不会修改事实。

A Section is a flat ordered object with soft remove/restore lifecycle. A
Placement is an independent relation, allowing one Item in multiple Sections.
An active Item without an effective Placement is projected into virtual
`Unsectioned`; no database row is created. Freshness deterministically compares
the current READY Revision with Working state and SHA-256 and returns `CURRENT`,
`WORKSPACE_UPDATED`, `WORKSPACE_MISSING`, or `WORKSPACE_UNREADABLE`. Queries do
not mutate facts.

## 3. Retention 与安全清理 / Retention and safe cleanup

清理候选遵守 D114-B：Current Revision、每个 Item 的上一 READY Revision、人工保护
Revision、Annotation 引用 Revision 均不得删除。Preview 返回候选、预计可回收字节和
绑定 `context_revision` 与候选身份的 Token。Execute 必须显式确认、匹配当前
`context_revision` 并重新计算相同 Token；任何中间变化都会拒绝陈旧预览。

Cleanup candidates follow D114-B: the current Revision, the preceding READY
Revision for each Item, manually protected Revisions, and Annotation-referenced
Revisions cannot be deleted. Preview returns candidates, estimated reclaimable
bytes, and a token bound to `context_revision` and candidate identities. Execute
requires explicit confirmation, the current `context_revision`, and a freshly
recomputed matching token; any intervening change rejects the stale preview.

数据库先在单一事务中删除符合条件的 Revision 和无引用 Content Object 记录，再删除
物理对象。物理删除失败不会伪造回滚已经提交的事实，而是返回 Orphan Key 并追加 Warning
Event，供后续恢复扫描处理。Original、Source、Workspace 结构和 Working 字节不被修改。

The database first removes eligible Revisions and unreferenced Content Object
rows in one transaction, then removes physical objects. A physical deletion
failure does not fake a rollback of committed facts; it returns orphan keys and
appends a warning Event for later recovery inspection. Original, Source,
Workspace structure, and Working bytes are never modified.

## 4. Persistence、State 与 Event / Persistence, state, and events

`0011_context_actions` 扩展结构化 Event/Error 词汇，并把 Processing Event 对 Revision
和 Content Object 的两个外键改为软历史引用，使受控 Retention 不会破坏 append-only
Event。其他 Context 外键和 Project 所有权约束保持不变。

`0011_context_actions` extends the structured Event/Error vocabulary and changes
the two Processing Event foreign keys to Revisions and Content Objects into soft
historical references so controlled retention cannot break append-only Events.
All other Context foreign keys and Project-ownership constraints remain intact.

关键 Event 包括 Item Promote/Remove/Restore、Revision Advance/Protect/Unprotect、
Section Create/Rename/Reorder/Remove/Restore、Placement Create/Reorder/Remove、
Annotation Create/Update、Cleanup Preview/Complete/Failure 和 Context Write
Conflict。所有写操作使用独立 `context_revision` 乐观并发；冲突写入 Warning Event 后
返回结构化 `CONTEXT_WRITE_CONFLICT`。

Key Events cover Item promotion/removal/restoration, Revision advancement and
protection, Section create/rename/reorder/remove/restore, Placement
create/reorder/remove, Annotation create/update, cleanup preview/completion/
failure, and Context write conflict. Every write uses the independent
`context_revision` optimistic-concurrency counter; a conflict appends a warning
Event and returns structured `CONTEXT_WRITE_CONFLICT`.

## 5. Application Contract 与权限 / Application contracts and permission

能力通过 typed in-process Application requests/results 暴露，并由 `PigApplication`
统一编排。它们是未来 Tool Contract 的候选边界，但本阶段没有公开 API、CLI、MCP 或
Agent Tool。Actor 必填；所有实体必须属于请求 Project；文本、Ordinal、生命周期、
Revision 引用和 Project Model Version 均在 Application 层校验。

Capabilities are exposed through typed in-process Application requests/results
and orchestrated by `PigApplication`. They are candidate boundaries for future
Tool contracts, but this stage exposes no public API, CLI, MCP, or Agent Tool.
Actor is required; every entity must belong to the requested Project; text,
ordinals, lifecycle, Revision references, and Project Model Version are validated
in the Application layer.

## 6. 测试证据 / Test evidence

新增与回归测试覆盖：Promote 幂等、虚拟 `Unsectioned`、多 Placement、Section 软删除/
恢复、Guidance 重启保持、Working 修改后的 Freshness、Item 移除/恢复不丢 Revision、
Current + Previous 保留、人工保护、陈旧 Cleanup Preview 拒绝、显式清理确认、结构化并发
冲突、Migration、Repository、Capture Core 和 Object Store 兼容性。

New and regression tests cover idempotent promotion, virtual `Unsectioned`,
multiple Placements, Section soft remove/restore, restart-safe guidance,
freshness after Working changes, Item remove/restore without losing Revisions,
current-plus-previous retention, manual protection, stale cleanup-preview
rejection, explicit cleanup confirmation, structured concurrency conflicts,
migrations, repositories, Capture Core, and Object Store compatibility.

完整测试命令 `.venv\Scripts\python.exe -m pytest -q` 的结果为 `201 passed, 95
skipped, 1 warning`。Skip 均为已由 ADR-010 取代的历史测试或宿主机不允许创建测试
Symlink；Warning 来自重复 ZIP Entry 的既有回归样例。

The full command `.venv\Scripts\python.exe -m pytest -q` completed with `201
passed, 95 skipped, 1 warning`. Skips are historical tests superseded by ADR-010
or host restrictions on test symlink creation; the warning comes from an
existing duplicate-ZIP-entry regression fixture.

## 7. 当前边界 / Current boundary

V2.1.3 已完成并停止在 Application、Domain、Persistence 和 Query 边界。V2.1.4
Minimum UI 没有由本阶段自动授权，但产品负责人已于 2026-10-08 另行评审批准；其范围
以 `PIG-V2.1.4-minimum-ui-plan.md` 为准。Docling、正文解析、FTS、Embedding、Vector
Store、RAG、模型调用、平台 Adapter、MCP、Agent 与 Automation 仍然不做。

V2.1.3 is complete and stops at the Application, Domain, Persistence, and Query
boundaries. It did not automatically authorize V2.1.4 Minimum UI, but the product
owner separately reviewed and approved that stage on 2026-10-08 under
`PIG-V2.1.4-minimum-ui-plan.md`. Docling, content parsing, FTS, embeddings,
vector stores, RAG, model calls, platform adapters, MCP, Agents, and Automation
remain out of scope.
