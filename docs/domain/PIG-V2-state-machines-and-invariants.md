# PIG V2 状态机与不变量 / PIG V2 State Machines and Invariants

- 状态：V2.1 本轮验收通过；V2.2 Export 状态机仍是规划 / Status: V2.1 accepted in this run; V2.2 Export state machine remains planned
- 日期：2026-10-07 / Date: 2026-10-07
- 约束决策：`ADR-010`、`ADR-024`、`ADR-025` / Governing decisions: `ADR-010`, `ADR-024`, `ADR-025`

## 0. Project 升级 / Project upgrade

```text
V1_DETECTED -> PREFLIGHTED -> BACKED_UP -> MIGRATING -> VALIDATING -> V2_READY
       \             \              \           \          -> FAILED
        -> DECLINED   -> FAILED       -> FAILED    -> FAILED
```

只有已验证备份存在且 Migration 后 V1 事实校验通过，才能写入新模型版本。`FAILED` Project
必须停止写入，保留数据库和备份，并通过显式重试或恢复处理；不得继续半升级运行。

The new model version is written only after a verified backup exists and
post-migration validation confirms V1 facts. A `FAILED` Project becomes
read-only, retains the database and backup, and requires explicit retry or
restore; it cannot continue in a partial upgrade state.

## 1. Context Item 生命周期 / Context Item lifecycle

```text
ACTIVE -> REMOVED
REMOVED -> ACTIVE
```

`REMOVED` 只把 Item 从当前 Context 隐藏，不删除 Workspace Item、Context Revision、
Annotation、Analysis 或 Original。永久清理需要未来独立保留策略。

`REMOVED` only hides the Item from the active Context. It does not delete the
Workspace Item, Context Revisions, Annotations, Analyses, or Originals. Permanent
cleanup requires a future retention policy.

## 2. Context Revision 捕获 / Context Revision capture

```text
PENDING -> CAPTURING -> READY
                    -> FAILED
PENDING -> CANCELLED
CAPTURING -> CANCELLED_AT_SAFE_POINT
```

只有 `READY` Revision 可以成为 `current_context_revision_id`、Extraction 输入或 Context
Pack 文件条目。`FAILED` 和 `CANCELLED` 不得发布部分字节。

Only a `READY` Revision may become `current_context_revision_id`, extraction
input, or a Context Pack file entry. `FAILED` and `CANCELLED` cannot publish
partial bytes.

捕获前容量预检结果为：

Capture capacity preflight produces:

```text
WITHIN_LIMIT
SOFT_QUOTA_WARNING
BLOCKED_MINIMUM_FREE_SPACE
```

`SOFT_QUOTA_WARNING` 允许用户知情后继续；`BLOCKED_MINIMUM_FREE_SPACE` 必须阻止捕获。
任何结果都不得自动清理 Revision。

`SOFT_QUOTA_WARNING` permits informed continuation;
`BLOCKED_MINIMUM_FREE_SPACE` blocks capture. No result may automatically clean
up Revisions.

## 2.1 Context Content Object / Context Content Object

```text
STAGED -> AVAILABLE
STAGED -> DISCARDED
AVAILABLE -> ORPHAN_CANDIDATE
AVAILABLE -> MISSING
ORPHAN_CANDIDATE -> AVAILABLE
```

只有数据库中被 READY Revision 引用且 Hash/Size 匹配的 `AVAILABLE` 对象属于有效
Context。无引用文件只可成为恢复或清理候选，不能由目录扫描自动提升为领域对象。

Only an `AVAILABLE` object referenced by a READY Revision and matching its hash
and size belongs to valid Context. An unreferenced file can only become a
recovery or cleanup candidate and cannot be promoted to a domain object by a
directory scan.

## 2.2 Section 与有效 Placement / Section and effective Placement

```text
Section: ACTIVE -> REMOVED -> ACTIVE
Placement: ACTIVE -> REMOVED -> ACTIVE
```

Placement 只有在自身和所属 Section 均为 `ACTIVE` 时才有效。Active Context Item 没有
有效 Placement 时投影到虚拟 `Unsectioned`。删除 Section 不级联删除 Placement 或 Item；
恢复 Section 会恢复仍为 Active 的 Placement 可见性。

A Placement is effective only when both it and its Section are `ACTIVE`. An
active Context Item with no effective Placement is projected into virtual
`Unsectioned`. Removing a Section does not cascade-delete Placements or Items;
restoring it restores visibility of Placements that remain active.

## 2.3 Revision 保留资格 / Revision retention eligibility

```text
RETAIN_CURRENT
RETAIN_PREVIOUS
RETAIN_REFERENCED
RETAIN_MANUALLY_PROTECTED
CLEANUP_CANDIDATE
```

以上是可重复计算的资格而不是删除状态。Current、Previous、被保留 Analysis/Citation/
Context Pack 引用或人工保护的 Revision 不能成为 `CLEANUP_CANDIDATE`。清理预览不改变
任何 Revision。执行清理必须由用户明确确认，并在同一受控写流程中重新校验预览和
全部保护关系。

These are recomputable eligibility results rather than deletion states. Current,
previous, retained Analysis/Citation/Context Pack referenced, or manually
protected Revisions cannot become `CLEANUP_CANDIDATE`. A cleanup preview changes
nothing. Execution requires explicit user confirmation and must revalidate the
preview and all protections in the same controlled write flow.

## 2.4 乐观并发 / Optimistic concurrency

```text
expected_context_revision == stored_context_revision -> commit + increment
expected_context_revision != stored_context_revision -> CONTEXT_CONFLICT
capture source changed after preflight -> WORKSPACE_CHANGED_DURING_CAPTURE
```

Context 与 Workspace Revision 是独立的 Project 计数器。失败或回滚的事务不得推进任一
计数器；UI 不得通过覆盖最新值来隐藏冲突。

Context and Workspace revisions are independent Project counters. Failed or
rolled-back transactions advance neither counter, and the UI cannot hide a
conflict by overwriting the latest value.

## 3. Context 新鲜度 / Context freshness

```text
CURRENT
WORKSPACE_UPDATED
WORKSPACE_MISSING
WORKSPACE_UNREADABLE
```

Freshness 是 Context Revision 与最新 Workspace Observation 的比较结果，不替代
Revision 捕获状态。文件改变只产生 `WORKSPACE_UPDATED`；系统不得自动推进 Context
Revision。

Freshness compares a Context Revision with the latest Workspace observation and
does not replace Revision capture state. A changed file produces
`WORKSPACE_UPDATED`; the system cannot advance the Context Revision automatically.

## 4. Extraction Run / Extraction Run

```text
PENDING -> RUNNING -> SUCCEEDED
                   -> PARTIAL
                   -> UNSUPPORTED
                   -> FAILED
PENDING/RUNNING -> CANCELLED_AT_SAFE_POINT
```

`PARTIAL` 必须记录缺失的页、Sheet、元素或能力；不得伪装成完整成功。相同 Revision、
Extractor 名称、Extractor 版本和配置 Hash 构成幂等键候选。

`PARTIAL` records missing pages, sheets, elements, or capabilities and cannot
pretend to be complete success. Revision, extractor name, extractor version,
and configuration hash form the candidate idempotency identity.

## 5. Index State / Index State

```text
NOT_INDEXED -> INDEXING -> READY
                         -> FAILED
READY -> STALE -> INDEXING
```

Index 是派生数据，可以删除和重建。删除 Index 不得删除 Canonical Content、Context
Revision 或 Annotation。

An Index is derived data and may be deleted and rebuilt. Deleting an Index
cannot delete Canonical Content, Context Revisions, or Annotations.

## 6. Analysis Run / Analysis Run

```text
QUEUED -> RUNNING -> SUCCEEDED
                  -> FAILED
QUEUED/RUNNING -> CANCELLED_AT_SAFE_POINT
```

Analysis 执行状态与结果新鲜度分离：

Analysis execution state is separate from result freshness:

```text
CURRENT_INPUTS
CONTEXT_REVISION_ADVANCED
WORKSPACE_UPDATED_BEYOND_CONTEXT
INPUT_UNAVAILABLE
```

已成功结果继续绑定原输入 Revision。新版本只改变新鲜度，不得改写旧结果或 Citation。

A successful result remains bound to its original input Revisions. A newer
version changes freshness and cannot rewrite the old result or Citations.

## 7. Context Pack Export / Context Pack Export

```text
PENDING -> PREFLIGHTED -> RUNNING -> SUCCEEDED
                                  -> FAILED
PENDING/PREFLIGHTED/RUNNING -> CANCELLED_AT_SAFE_POINT
```

`PREFLIGHTED` 必须列出输出路径、文件数量、总大小、包含的 Revision、Annotation 和
Analysis，以及冲突策略。输出使用临时目录或临时文件并原子发布；失败不得留下看似
成功的完整目标。

`PREFLIGHTED` lists the destination, file count, total bytes, included Revisions,
Annotations, and Analyses, plus conflict policy. Output uses a temporary path and
atomic publication; failure cannot leave a target that appears complete.

## 8. 领域不变量 / Domain invariants

1. `ContextItem.project_id`、`WorkspaceItem.project_id` 和所有 Placement/Revision 必须相同。
2. 一个 Context Item 最多有一个 current Revision，但可以保留多个不可变历史 Revision。
3. Revision 的 `content_sha256`、`size_bytes` 和已发布字节必须一致。
4. Workspace 修改不得改变任何既有 Revision 字节或 Hash。
5. Context Placement 不得改变 Workspace parent、Source Relationship 或物理路径。
6. 同一 Item 在同一 Section 中最多一个 Active Placement。
7. Annotation 必须标识人为来源；AI 输出不得伪装为人工 Annotation。
8. Extraction、Index 和 Analysis 必须绑定明确 Revision，不得只绑定文件名或可变路径。
9. Citation 必须属于 Analysis 的输入闭包，不能引用未提供给该 Analysis 的 Revision。
10. AI 结果不得成为 Project、文件版本、路径或权限的唯一事实来源。
11. 远程模型调用必须由明确用户 Action 发起并记录外发范围。
12. API Secret、OAuth Token 和模型凭据不得进入 Project Database、Event Metadata 或日志。
13. 删除派生数据不得级联删除 Context、Workspace、Source 或 Original。
14. 取消只能发生在安全点；已提交的 Domain 事实必须保持可重开一致性。
15. UI 不得自行推进 Revision、Analysis、Export 或权限状态。
16. Project 的 `context_revision` 与 `workspace_revision` 相互独立且只能单调递增。
17. 一个 Project 内 `(project_id, sha256)` 最多对应一个有效 Content Object；不同
    Project 不共享对象所有权。
18. READY Revision 必须引用 Hash/Size 一致的 AVAILABLE Content Object。
19. Materialized Item 捕获当前 Working 字节；Virtual Item 捕获 Source 字节且不得仅为
    Context 强制创建 Working Artifact。
20. Section 是扁平结构；V2.1 不允许 Section parent。
21. 删除 Section 不得删除 Context Item、Revision、Annotation、Workspace 或 Original。
22. `Unsectioned` 是 Query Projection，不是持久化 Section 或事实来源。
23. 默认保留 Current 和 Previous Revision；引用或人工保护优先于数量上限。
24. 容量预检不得通过自动删除数据来满足门限。

1. `ContextItem.project_id`, `WorkspaceItem.project_id`, and every related
   Placement/Revision belong to the same Project.
2. A Context Item has at most one current Revision but may retain multiple
   immutable historical Revisions.
3. Revision `content_sha256`, `size_bytes`, and published bytes agree.
4. Workspace modification cannot change any existing Revision bytes or hash.
5. Context Placement cannot change Workspace parent, Source relationships, or
   physical paths.
6. One Item has at most one active Placement in one Section.
7. Annotation records human authorship; AI output cannot impersonate a human
   Annotation.
8. Extraction, Index, and Analysis bind to explicit Revisions rather than only
   a filename or mutable path.
9. A Citation belongs to the Analysis input closure and cannot reference a
   Revision that was not supplied to that Analysis.
10. AI output cannot be the sole source of Project, file-version, path, or
    permission facts.
11. A remote model call is initiated by an explicit user Action and records its
    outbound scope.
12. API secrets, OAuth tokens, and model credentials never enter the Project
    database, Event metadata, or logs.
13. Deleting derived data cannot cascade into Context, Workspace, Source, or
    Original data.
14. Cancellation occurs only at safe points; committed facts remain consistent
    after reopen.
15. UI cannot advance Revision, Analysis, Export, or permission state itself.
16. Project `context_revision` and `workspace_revision` are independent and
    monotonic.
17. Within one Project, `(project_id, sha256)` identifies at most one valid
    Content Object; object ownership is not shared across Projects.
18. A READY Revision references an AVAILABLE Content Object with matching hash
    and size.
19. A materialized Item captures current Working bytes; a virtual Item captures
    Source bytes and cannot force a Working Artifact merely for Context.
20. Sections are flat; V2.1 does not allow Section parents.
21. Removing a Section cannot delete Context Items, Revisions, Annotations,
    Workspace, or Originals.
22. `Unsectioned` is a query projection, not a persisted Section or fact source.
23. Current and previous Revisions are retained by default, and reference or
    manual protection overrides the count limit.
24. Capacity preflight cannot satisfy a gate by automatically deleting data.

## 9. 结构化事件 / Structured events

V2 至少规划以下业务事件：

V2 plans at least these business events:

- `ContextItemPromoted`
- `ContextItemRemoved`
- `ContextItemRestored`
- `ContextPlacementChanged`
- `ContextAnnotationCreated`
- `ContextAnnotationUpdated`
- `ContextRevisionCaptureStarted`
- `ContextRevisionCreated`
- `ContextRevisionCaptureFailed`
- `ContextRevisionAdvanced`
- `ContextBecameOutdated`
- `ProjectContextUpgradeRequested`
- `ProjectContextUpgradeStarted`
- `ProjectContextUpgradeCompleted`
- `ProjectContextUpgradeFailed`
- `ContextCaptureBlockedByCapacity`
- `ContextContentObjectReused`
- `ContextContentObjectPublished`
- `ContextContentObjectOrphanDetected`
- `ContextSectionCreated`
- `ContextSectionRenamed`
- `ContextSectionRemoved`
- `ContextSectionRestored`
- `ContextRevisionProtected`
- `ContextRevisionUnprotected`
- `ContextCleanupPreviewed`
- `ContextCleanupConfirmed`
- `ContextRevisionCleanupCompleted`
- `ContextRevisionCleanupFailed`
- `ContextWriteConflict`
- `WorkspaceChangedDuringCapture`
- `ExtractionStarted`
- `ExtractionCompleted`
- `ExtractionFailed`
- `IndexBuilt`
- `AnalysisRequested`
- `AnalysisCompleted`
- `AnalysisFailed`
- `ContextPackExportRequested`
- `ContextPackExportCompleted`
- `ContextPackExportFailed`

业务 Event 使用稳定 ID、Project/Object ID、Actor、UTC Timestamp、Correlation ID 和安全
Metadata。模型原始响应、Secret 和完整文档内容不得写入 Event Metadata。

Business Events use stable IDs, Project/Object IDs, actor, UTC timestamp,
correlation ID, and safe metadata. Raw model responses, secrets, and full
document contents cannot enter Event metadata.
