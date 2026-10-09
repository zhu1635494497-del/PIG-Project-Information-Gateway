# PIG V2.1.2 捕获核心实施记录 / PIG V2.1.2 Capture Core Implementation Record

- 状态：已完成 / Status: Complete
- 日期：2026-10-08 / Date: 2026-10-08
- Migration：`0010_context_capture_core` / Migration: `0010_context_capture_core`
- 约束决策：`ADR-024`、`ADR-025` / Governing decisions: `ADR-024`, `ADR-025`

## 1. 实施范围 / Implemented scope

V2.1.2 实现 Project 内内容寻址对象存储、Materialized Working 捕获、Virtual Source
直接捕获、流式 SHA-256/Size、容量门、原子发布、同 Project 去重、安全点取消以及
Orphan/Missing 恢复扫描。它没有实现 Promote、Section、Placement、Annotation、
Freshness、清理、UI、内容解析或 AI。

V2.1.2 implements a Project-local content-addressed object store, materialized
Working capture, direct virtual Source capture, streaming SHA-256/size,
capacity gates, atomic publication, per-Project deduplication, safe-point
cancellation, and orphan/missing recovery inspection. It does not implement
promotion, Sections, Placements, Annotations, freshness, cleanup, UI, content
extraction, or AI.

## 2. Domain、Flow 与边界 / Domain, flow, and boundaries

### Domain

本阶段使用已有 `ContextItem`、`ContextRevision`、`ContextContentObject`、
`WorkspaceItem`、`WorkingArtifact` 与 `SourceNode`。测试通过 Repository 预置
`ContextItem`；用户可见 Promote 属于 V2.1.3，不在本阶段伪造。

This stage uses the existing `ContextItem`, `ContextRevision`,
`ContextContentObject`, `WorkspaceItem`, `WorkingArtifact`, and `SourceNode`.
Tests seed a `ContextItem` through the repository; user-facing promotion belongs
to V2.1.3 and is not simulated as a public action here.

### Flow

```text
Existing Context Item
  -> validate Project, Workspace revision, and Context revision
  -> choose Working or Source according to D118-B
  -> capacity preflight
  -> PENDING -> CAPTURING
  -> stream bytes into operation staging and hash
  -> verify source/concurrency again
  -> atomically publish or reuse context/objects/<prefix>/<sha256>
  -> create/reuse Content Object + READY Revision
  -> update Item current revision + advance context_revision
```

Materialized Item 先复用现有 Working refresh，再读取当前 Working 字节。Virtual Item
复用现有容器 locator/materialization 链，直接写入 Context staging，不创建
`WorkingArtifact`，也不调用 Host Application。

A materialized Item first reuses the existing Working refresh and then reads the
current Working bytes. A virtual Item reuses the existing container locator and
materialization chain and writes directly to Context staging without creating a
`WorkingArtifact` or invoking a Host Application.

### State and lineage

Revision 使用 `PENDING -> CAPTURING -> READY/FAILED/CANCELLED_AT_SAFE_POINT`。
READY Revision 固定引用 Content Object；Working 路径保存 `source_working_artifact_id`，
Virtual 路径保存 `source_node_id`。成功捕获才推进 Project `context_revision`。

Revisions use `PENDING -> CAPTURING -> READY/FAILED/CANCELLED_AT_SAFE_POINT`.
A READY Revision fixes its Content Object reference. Working capture stores
`source_working_artifact_id`, while virtual capture stores `source_node_id`.
Only a successful capture advances Project `context_revision`.

### Log, permission, Tool, AI, Automation, and UI

捕获预检、开始、完成、失败、取消、容量阻断、对象发布/复用和 Orphan/Missing 检测均
记录结构化 Event。捕获只读 Original/Source/Working；只写 Project 内 staging、Context
Object Store 和 SQLite。当前能力只通过 typed in-process Application Contract 暴露，
没有公共 Tool/API/MCP；AI、Automation 和 UI 均无变化。

Capture preflight, start, completion, failure, cancellation, capacity blocking,
object publication/reuse, and orphan/missing detection produce structured
Events. Capture reads Original/Source/Working only and writes only Project-local
staging, the Context Object Store, and SQLite. The capability is exposed only as
a typed in-process Application Contract, with no public Tool/API/MCP and no AI,
Automation, or UI change.

## 3. Storage 与安全 / Storage and safety

- Object Key 固定为 `context/objects/<sha256 前两位>/<sha256>`；文件名不参与路径。
- 写入先进入 `.staging/context/<operation-id>/content`，同卷 hard-link 发布保证不覆盖。
- 同名对象存在时重新校验 Size 与 SHA-256；损坏对象拒绝复用。
- 默认软配额为 10 GiB，只产生结果警告；预测剩余空间低于 2 GiB 时写入前阻断。
- 取消只在流式写入安全点生效；数据库提交后不再把 READY Revision 改为取消。
- 扫描只标记/报告 Missing 与 Orphan Candidate，不自动删除数据。

- Object keys are fixed as `context/objects/<first-two-sha256>/<sha256>`; filenames
  never participate in paths.
- Writes first enter `.staging/context/<operation-id>/content`; same-volume
  hard-link publication is non-overwriting.
- An existing object is revalidated by size and SHA-256; corrupt objects are not reused.
- The default 10 GiB soft quota produces a result warning only; capture is
  blocked before writing when projected free space would fall below 2 GiB.
- Cancellation is honored only at streaming safe points; a READY Revision is not
  relabeled as cancelled after database commit.
- Inspection reports/marks Missing and Orphan Candidate states and never deletes data.

## 4. Persistence 与 Migration / Persistence and migration

`0010_context_capture_core` 将捕获相关 Event Type 和 Error Code 加入 SQLite 约束。
V2.1 表结构继续使用 `0009_project_context_foundation`。升级入口现在接受
`0008`、`0009`，并把数据库推进到 `0010`；升级仍要求备份和校验。

`0010_context_capture_core` adds capture Event Types and Error Codes to SQLite
constraints. V2.1 table structures remain those introduced by
`0009_project_context_foundation`. The upgrade entry now accepts `0008` and
`0009` and advances the database to `0010`, still requiring backup and validation.

## 5. 测试证据 / Test evidence

新增测试覆盖：

- Content Object 发布、同 Project 去重、损坏对象拒绝；
- staging 取消清理；
- Virtual 普通文件和压缩包内 Child 直接 Source 捕获；
- Working 修改后捕获和重复 Revision 复用对象；
- 缺失 Working 形成 FAILED Revision 且不推进 `context_revision`；
- Workspace 乐观并发冲突；
- 容量门在 Revision 创建前阻断；
- Orphan/Missing 扫描和 Missing 状态持久化；
- `0001 -> 0010` Migration 与 V1 升级回归。

New coverage includes:

- Content Object publication, per-Project deduplication, and corrupt-object rejection;
- cancellation cleanup of staging;
- direct Source capture for a normal virtual file and a child inside an archive;
- capture of modified Working bytes and object reuse across Revisions;
- FAILED Revision behavior for missing Working bytes without advancing `context_revision`;
- Workspace optimistic-concurrency conflict;
- capacity blocking before Revision creation;
- orphan/missing inspection and persisted Missing status;
- `0001 -> 0010` migration and V1 upgrade regression.

## 6. 当前边界 / Current boundary

V2.1.2 已完成并由 V2.1.3 Context Actions 继续使用。本记录只描述 Capture Core；
当前授权边界以规划索引和 V2.1.3 实施记录为准。

V2.1.2 is complete and is consumed by V2.1.3 Context Actions. This record only
describes Capture Core; the current authorization boundary is defined by the
planning indexes and the V2.1.3 implementation record.
