# PIG V2 Project Context 领域模型 / PIG V2 Project Context Domain Model

- 状态：V2.1 对象已实施；V2.2 Export 对象仍是规划 / Status: V2.1 objects implemented; V2.2 Export objects remain planned
- 版本：2.2-plan / Version: 2.2-plan
- 日期：2026-10-07 / Date: 2026-10-07
- 约束决策：`ADR-010`、`ADR-024`、`ADR-025` / Governing decisions: `ADR-010`, `ADR-024`, `ADR-025`

## 1. 聚合关系 / Aggregate relationships

`Project` 继续是隔离边界。V2 不新增第二个 Project 或第二套 Workspace，而是在现有
Workspace 之上增加 Context 聚合和可重建的 Content/Analysis 派生聚合。

`Project` remains the isolation boundary. V2 creates neither a second Project
nor a second Workspace. It adds a Context aggregate above the current Workspace
and rebuildable Content/Analysis derivative aggregates.

```text
Project
├── context_revision
├── V1 Original Snapshot / Source Structure / Workspace Tree
├── ContextSection
├── ContextItem -- references --> WorkspaceItem
│   ├── ContextPlacement -- references --> ContextSection
│   ├── ContextRevision -- references --> ContextContentObject
│   └── Annotation
├── ContextContentObject -- owns immutable object bytes
├── ExtractionRun
│   └── ContentDocument
│       └── ContentElement
├── AnalysisRun
│   ├── AnalysisInput -- references --> ContextRevision
│   ├── AnalysisResult
│   └── Citation -- references --> ContentElement / ContextRevision
└── ContextPackExport
    └── ContextPackEntry -- references --> ContextRevision / result
```

## 2. 核心领域对象 / Core domain objects

### Project

沿用 V1 身份、SQLite Database、存储边界和 `workspace_revision`，并新增独立、单调递增
的 `context_revision`。V2 Migration 只增加 Context/Content/Analysis 数据，不重写 V1
Original、Source、Workspace 或 Working 事实。

Retains the V1 identity, SQLite database, storage boundary, and
`workspace_revision`, and adds an independent monotonic `context_revision`. V2
migrations add Context/Content/Analysis data without rewriting V1 Original,
Source, Workspace, or Working facts.

### ContextSection

表示用户定义的主题分组，而不是物理文件夹。V2.1 只支持扁平、有序 Section，不包含
`parent_section_id`。建议字段：`id`、`project_id`、`name`、`description`、`ordinal`、
`lifecycle_status` 和时间字段。删除为软删除。

Represents a user-defined thematic grouping rather than a physical folder. V2.1
supports only flat, ordered Sections and has no `parent_section_id`. Suggested
fields include `id`, `project_id`, `name`, `description`, `ordinal`,
`lifecycle_status`, and timestamps. Deletion is soft.

### ContextItem

表示一个被提升为核心材料的 Project 对象。首期只允许引用同 Project 的 Active
Terminal `WorkspaceItem`。建议字段：`id`、`project_id`、`workspace_item_id`、
`title`、`purpose`、`lifecycle_status`、`current_context_revision_id` 和时间字段。

Represents a Project object promoted as core material. Initially it may reference
only an Active terminal `WorkspaceItem` in the same Project. Suggested fields
include `id`, `project_id`, `workspace_item_id`, `title`, `purpose`,
`lifecycle_status`, `current_context_revision_id`, and timestamps.

### ContextPlacement

显式表达 Context Item 在 Section 中的位置和顺序。它是多对多关系对象，关键字段为
`context_item_id`、`context_section_id`、`ordinal` 和可选展示说明。同一 Item 在同一
Section 中不得重复 Placement。

Explicitly represents the position and order of a Context Item in a Section. It
is a many-to-many relationship object with `context_item_id`,
`context_section_id`, `ordinal`, and optional presentation guidance. One Item
cannot have duplicate placements in the same Section.

被软删除 Section 下的 Placement 继续保存但不生效。没有有效 Placement 的 Active Item
通过 Query 投影到虚拟 `Unsectioned`；`Unsectioned` 不是数据库 Section。

Placements under a soft-deleted Section remain stored but ineffective. An active
Item with no effective Placement is projected by queries into virtual
`Unsectioned`; `Unsectioned` is not a database Section.

### ContextContentObject

表示一个 Project 内按内容寻址的不可变字节对象。建议字段：`id`、`project_id`、
`sha256`、`size_bytes`、`object_key`、`availability_status` 和时间字段；
`(project_id, sha256)` 唯一。跨 Project 不共享对象，数据库引用是所有权事实来源。

Represents immutable content-addressed bytes inside one Project. Suggested
fields include `id`, `project_id`, `sha256`, `size_bytes`, `object_key`,
`availability_status`, and timestamps, with unique `(project_id, sha256)`.
Objects are not shared across Projects, and database references are the ownership
source of truth.

### ContextRevision

表示用户明确采用的一组不可变文件字节。建议字段：`id`、`context_item_id`、
`content_object_id`、`source_kind`、可选 `source_working_artifact_id`、可选
`source_node_id`、`captured_workspace_revision`、`source_observed_sha256`、
`capture_status`、保护标记/原因、`created_by` 和 `created_at`。Revision 不允许原地
修改；更新 Context 必须创建新 Revision 并移动 current pointer。

Represents immutable file bytes explicitly adopted by the user. Suggested fields
include `id`, `context_item_id`, `content_object_id`, `source_kind`, optional
`source_working_artifact_id`, optional `source_node_id`,
`captured_workspace_revision`, `source_observed_sha256`, `capture_status`,
protection flag/reason, `created_by`, and `created_at`. A Revision is never
updated in place; updating Context creates a new Revision and advances the
current pointer.

### Annotation

保存人工说明，不与 AI 输出混合。首期支持 Item 级说明；段落/单元格锚点说明延后。
建议字段：`id`、`project_id`、`context_item_id`、可选 `context_revision_id`、`kind`、
`body`、`author`、`created_at`、`updated_at`。

Stores human guidance separately from AI output. Initial scope supports Item-level
guidance; paragraph/cell-anchored annotations are deferred. Suggested fields
include `id`, `project_id`, `context_item_id`, optional `context_revision_id`,
`kind`, `body`, `author`, `created_at`, and `updated_at`.

### ExtractionRun

表示对一个 Context Revision 的一次确定性内容提取。关键字段包括 `id`、
`context_revision_id`、`extractor_name`、`extractor_version`、`status`、计数、错误码、
时间和 `correlation_id`。相同输入与 Extractor 版本可以幂等复用。

Represents one deterministic extraction of a Context Revision. Key fields include
`id`, `context_revision_id`, `extractor_name`, `extractor_version`, `status`,
counts, error code, timestamps, and `correlation_id`. The same input and
extractor version may be reused idempotently.

### ContentDocument 与 ContentElement

`ContentDocument` 是某 Revision 的 PIG Canonical Content 根。`ContentElement` 是有序、
可寻址的内容单元，类型可包括 `HEADING`、`PARAGRAPH`、`TABLE`、`SHEET_RANGE`、
`SLIDE_TEXT`、`EMAIL_HEADER` 和 `EMAIL_BODY`。Locator 使用显式字段或 typed value
object 表达页码、Sheet、Cell Range、Slide、段落或邮件字段，不得只保存自由文本。

`ContentDocument` is the PIG Canonical Content root for one Revision.
`ContentElement` is an ordered, addressable unit such as `HEADING`, `PARAGRAPH`,
`TABLE`, `SHEET_RANGE`, `SLIDE_TEXT`, `EMAIL_HEADER`, or `EMAIL_BODY`. A Locator
uses explicit fields or a typed value object for page, sheet, cell range, slide,
paragraph, or email field rather than only free text.

### AnalysisRun、AnalysisInput 与 AnalysisResult

`AnalysisRun` 表示一次 Typed AI Action；`AnalysisInput` 显式列出输入 Revision；
`AnalysisResult` 保存通过 Schema 校验的派生输出。关键事实包括 Prompt 名称/版本、
Provider、Model、输入 Hash、状态、Token/费用（可得时）、错误和时间。自由文本可以是
结果字段，但不得替代输入关系和 Citation。

`AnalysisRun` represents one typed AI action; `AnalysisInput` explicitly lists
input Revisions; `AnalysisResult` stores schema-validated derived output. Core
facts include prompt name/version, provider, model, input hash, state,
token/cost data when available, errors, and timestamps. Free text may be a
result field but cannot replace input relationships or Citations.

### Citation

将一个 Analysis Result 的具体 Claim 绑定到 `ContextRevision` 和可选
`ContentElement`。建议字段：`analysis_result_id`、`claim_path`、
`context_revision_id`、可选 `content_element_id`、`locator_snapshot` 和摘录。摘录是
辅助显示，引用身份以关系和 Locator 为准。

Binds a specific claim in an Analysis Result to a `ContextRevision` and optional
`ContentElement`. Suggested fields include `analysis_result_id`, `claim_path`,
`context_revision_id`, optional `content_element_id`, `locator_snapshot`, and an
excerpt. The excerpt assists presentation; relationship identity and Locator
remain authoritative.

### ContextPackExport 与 ContextPackEntry

表示一次外部交付。Entry 必须列出导出的 Revision、Annotation、Analysis Result 和
Manifest 版本。导出不改变 Context 或 Workspace，输出目录不得成为 Project 受管存储。

Represents one external handoff. Entries explicitly list exported Revisions,
Annotations, Analysis Results, and manifest version. Export does not change
Context or Workspace, and its destination cannot become managed Project storage.

## 3. 来源与新鲜度 / Origin and freshness

权威来源链为：

The authoritative origin chain is:

```text
Citation
  -> ContentElement
  -> ExtractionRun
  -> ContextRevision
  -> ContextItem
  -> WorkspaceItem
  -> optional SourceNode chain
  -> OriginalSnapshot
```

`AnalysisRun.status = SUCCEEDED` 只说明执行成功，不说明它仍对应当前 Workspace。
新鲜度必须独立计算：当前 Context Revision 与 Workspace 最新 fingerprint 相同则为
`CURRENT`；否则为 `WORKSPACE_UPDATED`。旧结果不得被改写成针对新版本的结果。

`AnalysisRun.status = SUCCEEDED` means only that execution succeeded, not that
it still matches the current Workspace. Freshness is computed separately: it is
`CURRENT` when the current Context Revision matches the latest Workspace
fingerprint and `WORKSPACE_UPDATED` otherwise. An old result cannot be rewritten
to claim that it targets newer bytes.

V2.1 捕获来源由 Workspace 状态确定：已有 Working Artifact 时捕获刷新后的当前 Working
字节；Virtual Item 通过受控 Source Materialization 直接写入 Context Staging，不创建
Working Artifact。缺失或不可读的当前 Working 会阻止捕获，不静默回退。

V2.1 derives capture source from Workspace state. If a Working Artifact exists,
it captures refreshed current Working bytes. A virtual Item uses controlled
Source materialization directly into Context staging without creating a Working
Artifact. Missing or unreadable current Working bytes block capture rather than
silently falling back.

## 4. 保留与并发 / Retention and concurrency

每个 Context Item 默认保留 Current 和 Previous Revision。被保留 Analysis、Citation、
Context Pack 引用或被用户手动保护的 Revision 继续保留。其他更早 Revision 仅成为
Cleanup Candidate；V2.1 不自动删除。

Each Context Item retains its current and previous Revisions by default. A
Revision referenced by retained Analysis, Citation, or Context Pack records, or
manually protected by the user, remains retained. Other older Revisions become
Cleanup Candidates only; V2.1 never deletes them automatically.

Context 写操作校验 Project 的预期 `context_revision`；捕获同时校验预期 Workspace
状态。Context 写入与 Workspace 写入使用不同计数器，互不借用或重置。冲突必须返回
结构化结果供刷新和重试。

Context writes validate expected Project `context_revision`, while capture also
validates expected Workspace state. Context and Workspace writes use separate
counters that never reuse or reset one another. Conflicts return structured
results for refresh and retry.

## 5. 存储建议 / Storage recommendation

```text
<project-root>/
├── project.sqlite
├── originals/                 # existing V1 immutable storage
├── working/                   # existing V1 mutable storage
├── context/
│   └── objects/<hash-prefix>/<sha256>
├── derived/
│   ├── extraction/<run-id>/
│   └── analysis/<run-id>/
└── staging/                   # operation-scoped, recoverable cleanup
```

Context 对象发布采用 staging copy、流式 Hash、支持时 fsync 和原子 rename。同一 Project
内可以按内容地址去重。数据库行仍是所有权事实来源；磁盘上一个无引用路径不会自动
成为有效领域对象。

Context object publication uses copy-to-staging, streaming hash, fsync where
supported, and atomic rename. Content-addressed storage may deduplicate equal
bytes inside one Project. Database rows remain the ownership source of truth;
an unreferenced file path is not automatically a valid domain object.

默认每 Project 10 GiB 为软提醒阈值；预计发布后可用空间低于 2 GiB 时阻止新捕获。两个
值均属于 Project Context 配置，软阈值不触发自动清理。

The default soft-warning threshold is 10 GiB per Project. New capture is blocked
when projected free space after publication would fall below 2 GiB. Both values
belong to Project Context configuration, and the soft threshold does not trigger
automatic cleanup.

## 6. Application Contract 候选 / Candidate Application contracts

以下名称用于定义边界，不构成 V2.1 代码授权：

The following names define boundaries and do not authorize V2.1 code:

- `promote_workspace_item_to_context`
- `create_context_section`
- `place_context_item`
- `add_context_annotation`
- `capture_context_revision`
- `advance_context_revision`
- `remove_context_section`
- `restore_context_section`
- `protect_context_revision`
- `preview_context_revision_cleanup`
- `refresh_context_freshness`
- `export_context_pack`
- `extract_context_content`
- `search_context_content`
- `run_context_analysis`
- `get_analysis_with_citations`

这些首先是 typed in-process Application Contract；只有稳定后才评估公共 Tool、API
或 MCP 暴露。

These begin as typed in-process Application contracts. Public Tool, API, or MCP
exposure is considered only after the contracts are stable.
