# PIG V2.1.4 最小界面评审与实施计划 / PIG V2.1.4 Minimum UI Review and Implementation Plan

- 状态：已实施并通过自动化回归 / Status: Implemented with automated regression passing
- 日期：2026-10-08 / Date: 2026-10-08
- 上位决策：`ADR-024`、`ADR-025` D117-A、D111-A / Parent decisions: `ADR-024`, `ADR-025` D117-A, D111-A
- 授权边界：仅 V2.1.4 / Authorization boundary: V2.1.4 only

## 1. 评审结论 / Review conclusion

V2.1.1 至 V2.1.3 已提供 Upgrade、Schema、Capture、Context Action 和 Query 闭环，
V2.1.4 可以在不改变领域模型、不增加 Schema 和不引入新依赖的前提下实施。D117-A
已经确定同窗口双视图和最小三栏结构，因此本阶段不需要新的重大 ADR。

V2.1.1 through V2.1.3 already provide the Upgrade, Schema, Capture, Context
Action, and Query loop. V2.1.4 can therefore proceed without changing the domain
model, adding schema, or introducing dependencies. D117-A already fixes the
same-window dual-view and minimum three-pane structure, so no new major ADR is
required for this stage.

评审发现一个必须在 UI 接线前补齐的小缺口：现有 Promote Action 内部执行捕获预检，
但尚无独立只读 Contract 供确认对话框展示捕获来源、预计字节、容量警告和阻断原因。
V2.1.4 获准增加该 typed Preflight Query；它不得创建 Item、Revision、Event 或文件。

The review found one small gap that must be closed before UI wiring: the current
promotion action performs capture preflight internally, but there is no separate
read-only contract for a confirmation dialog to show capture source, estimated
bytes, capacity warnings, and blocking reasons. V2.1.4 may add this typed
preflight query. It cannot create an Item, Revision, Event, or file.

## 2. 影响说明 / Impact statement

### Domain and lineage

不新增领域对象。Workspace 和 Context 继续是两个不同投影；UI 不复制 Item，也不把
Section 当文件夹。现有 `WorkspaceItem -> SourceNode -> OriginalSnapshot` 与
`ContextItem -> ContextRevision -> ContextContentObject` 来源关系保持不变。

No domain object is added. Workspace and Context remain separate projections;
the UI neither duplicates Items nor treats Sections as folders. Existing
`WorkspaceItem -> SourceNode -> OriginalSnapshot` and
`ContextItem -> ContextRevision -> ContextContentObject` lineage remains intact.

### Flow and state

用户从 Workspace 右键发起 Promote，先查看 Preflight，再确认后台捕获；成功后按后端
结果刷新 Context。所有 Context 写操作携带当前 `context_revision`，Workspace 捕获同时
携带 `workspace_revision`。冲突、失败或取消只显示后端结果，不在 UI 保留虚假状态。

The user initiates promotion from the Workspace context menu, reviews preflight,
and confirms background capture. Context reloads from the backend result after
success. Every Context write carries the current `context_revision`, while
Workspace capture also carries `workspace_revision`. Conflict, failure, or
cancellation displays the backend outcome and leaves no fabricated UI state.

### Log, permission, Tool, AI, automation, and UI

业务 Event 继续只由 Application 层写入；UI 错误诊断进入 Debug Log。Promote、组织、
说明和版本更新是 Project 写操作；Upgrade 和 Cleanup 必须预览确认。UI 只调用 typed
in-process Contract，不发布公共 Tool/API/MCP。AI、Agent、Workflow、Automation 和模型
调用不参与。UI 仅增加同窗口视图切换和三栏 Context 工作区。

Business Events continue to be written only by the Application layer; UI
diagnostics go to debug logs. Promotion, organization, guidance, and revision
updates are Project writes; Upgrade and Cleanup require preview plus
confirmation. The UI invokes typed in-process contracts only and exposes no
public Tool, API, or MCP. AI, Agents, Workflows, Automation, and model calls do
not participate. UI work is limited to same-window switching and the three-pane
Context workspace.

## 3. 最小界面结构 / Minimum interface structure

```text
[ Workspace ] [ Project Context ]

Project Context
┌────────────────┬──────────────────────────┬────────────────────────┐
│ Sections       │ Context Items            │ Item Details           │
│ All            │ title                    │ Workspace origin       │
│ Section A      │ purpose                  │ current Revision       │
│ Section B      │ freshness                │ SHA-256 / captured at  │
│ Unsectioned    │ capture status           │ guidance               │
│                │                          │ placements / actions   │
└────────────────┴──────────────────────────┴────────────────────────┘
```

- `Workspace` 保持现有树、搜索、Deleted Items、详情和 Activity，不重新实现。
- `Project Context` 只有 Section、Item、Details 三栏，不增加 Dashboard 或额外导航。
- `All` 和 `Unsectioned` 是只读投影；`Unsectioned` 不持久化。
- Section 和 Item 列表使用 Qt Model/View，避免逐项重建大型 Widget。
- 选择只改变当前投影；所有写入成功后重新读取权威 Query Result。

- `Workspace` retains the current tree, search, Deleted Items, details, and
  Activity; it is not reimplemented.
- `Project Context` contains only Section, Item, and Details panes, without a
  dashboard or extra navigation.
- `All` and `Unsectioned` are read-only projections; `Unsectioned` is not persisted.
- Section and Item lists use Qt Model/View rather than rebuilding large item widgets.
- Selection changes only the current projection; every successful write reloads
  the authoritative query result.

## 4. 获准交互 / Authorized interactions

### Workspace entry

- 文件右键 `Add to Project Context`；Folder 和 Container View 不可 Promote。
- 对话框显示文件、Materialized Working 或 Virtual Source 捕获来源、预计大小、容量结果、
  可选 Title Override 和 Purpose。
- 确认后使用单一后台执行器运行 Promote；成功不强制切换视图。
- 已存在 Active Context Item 时显示“已加入”，重复动作保持幂等。

- File context menu action `Add to Project Context`; folders and Container Views
  are not promotable.
- The dialog shows the file, Materialized Working or Virtual Source capture
  source, estimated size, capacity result, and optional title override/purpose.
- Confirmation runs promotion on the single background executor; success does
  not force a view switch.
- An existing active Context Item appears as already added, and repetition stays
  idempotent.

### Context organization

- 创建、重命名、排序、软删除和恢复 Section；不支持嵌套。
- 把 Item 放入一个或多个 Section、调整 Placement 顺序、移除 Placement。
- Item 无有效 Placement 时自动显示在虚拟 `Unsectioned`。
- Item 支持软移除和恢复；不删除 Workspace、Original 或 Revision。

- Create, rename, order, soft-remove, and restore Sections; nesting is unsupported.
- Place an Item in one or more Sections, reorder Placements, and remove a Placement.
- An Item with no effective Placement automatically appears in virtual `Unsectioned`.
- Items support soft removal and restoration without deleting Workspace,
  Original, or Revisions.

### Details, freshness, and retention

- Details 显示 Workspace Origin、Current Revision、Hash、捕获时间、Freshness、Guidance
  和 Placements。
- Guidance 使用显式 Save，不在每次按键时写数据库。
- `WORKSPACE_UPDATED` 时提供 `Create New Revision`，后台执行且不覆盖旧 Revision。
- Revision 列表支持人工 Protect/Unprotect，并显示保护原因。
- Cleanup 必须先展示候选和预计回收空间，再以 Token 和显式确认执行；不提供自动清理。

- Details shows Workspace origin, current Revision, hash, capture time,
  freshness, guidance, and Placements.
- Guidance uses explicit Save and never writes on every keystroke.
- `WORKSPACE_UPDATED` exposes `Create New Revision`, running in the background
  without overwriting the older Revision.
- The Revision list supports manual Protect/Unprotect with a visible reason.
- Cleanup previews candidates and estimated reclaimed space before token-bound,
  explicit confirmation; automatic cleanup is not provided.

### Upgrade and error handling

- 打开未升级的当前 V1 Workbench Project 时，Workspace 仍可读；进入 Project Context
  时显示 Upgrade 说明、备份位置和确认入口。
- Upgrade 复用 V2.1.1 Preflight/Execute，不在 UI 直接运行 Migration。
- `CONTEXT_WRITE_CONFLICT` 刷新 Context 并提示用户重试；容量、缺失、不可读和取消显示
  结构化错误，不展示 Stack Trace。

- When a current V1 Workbench Project has not been upgraded, Workspace remains
  readable. Entering Project Context shows the upgrade explanation, backup
  location, and confirmation entry.
- Upgrade reuses V2.1.1 preflight/execute and never runs migrations directly in UI.
- `CONTEXT_WRITE_CONFLICT` reloads Context and asks the user to retry. Capacity,
  missing, unreadable, and cancellation outcomes show structured errors without
  exposing stack traces.

## 5. 实现边界 / Implementation boundary

为避免继续膨胀已有 `main_window.py`，Project Context 的 Qt Models、三栏 Widget 和对话框
应放在独立 UI 模块中，由 `MainWindow` 只负责 Project 会话、视图切换和共享后台执行。
这属于局部 UI 模块化，不是大规模重构；不得顺带重写 V1 Workspace UI。

To avoid further growth of the existing `main_window.py`, Project Context Qt
models, the three-pane widget, and dialogs should live in dedicated UI modules.
`MainWindow` remains responsible only for the Project session, view switching,
and shared background execution. This is local UI modularization, not a broad
refactor, and cannot be used to rewrite the V1 Workspace UI.

本阶段允许：

- 一个只读 `PreflightContextPromotion` Application Query；
- Context UI 专用 Qt Model/View 和对话框；
- 对现有单后台执行器增加 Context capture stage label；
- UI 自动化、响应性和 Application 接线测试。

This stage permits:

- one read-only `PreflightContextPromotion` Application query;
- Context-specific Qt models/views and dialogs;
- Context capture stage labels in the existing single background executor;
- UI automation, responsiveness, and Application-wiring tests.

本阶段不得新增 Schema/Migration、第三方 Dependency、文件正文预览、缩略图、时间线、
思维导图、内容搜索、AI Chat、RAG、模型设置、平台连接或多用户能力。

This stage cannot add schema/migrations, third-party dependencies, file-content
preview, thumbnails, timelines, mind maps, content search, AI chat, RAG, model
settings, platform connections, or multi-user capability.

## 6. 分段实施 / Implementation slices

1. **UI Contract**：补齐只读 Promote Preflight、错误映射和 Context UI ViewModel。
2. **Dual View Shell**：在同一窗口加入 Workspace/Project Context 切换，不改变 Workspace。
3. **Three Panes**：接入 Section、Item、Details Query 和选择联动。
4. **Actions**：接入 Promote、Section、Placement、Guidance、Revision 与 Item 生命周期。
5. **Safety UI**：接入 Upgrade、Protection、Cleanup Preview/Confirm、Conflict Reload、
   Background Progress/Cancel。
6. **Qualification**：UI 自动测试、完整回归和源码桌面人工验收准备。

1. **UI Contract**: add read-only promotion preflight, error mapping, and Context
   UI view models.
2. **Dual View Shell**: add Workspace/Project Context switching in the same
   window without changing Workspace behavior.
3. **Three Panes**: wire Section, Item, and Details queries with selection flow.
4. **Actions**: wire promotion, Section, Placement, Guidance, Revision, and Item
   lifecycle actions.
5. **Safety UI**: wire Upgrade, protection, cleanup preview/confirmation,
   conflict reload, and background progress/cancellation.
6. **Qualification**: UI automation, full regression, and source-desktop manual
   acceptance preparation.

这些是同一 V2.1.4 内的实施切片，不自动授权 V2.1.5。若实施发现需要改变领域模型、
Schema、Original Policy、后台执行模型或引入依赖，必须暂停并返回新的决策门。

These are implementation slices inside V2.1.4 and do not authorize V2.1.5. If
implementation requires a domain-model, schema, Original-policy, background-
execution-model, or dependency change, work must stop and return to a new
decision gate.

## 7. 测试与验收 / Tests and acceptance

最低自动化测试必须覆盖：

- 双视图切换不重建或破坏 Workspace Tree 状态；
- 只有 Active、Source-backed Terminal File 可显示 Promote；
- Preflight 为只读且与执行时容量/来源规则一致；
- Promote 和 Revision Capture 在后台运行，主线程心跳持续；
- Section、Placement、Unsectioned、Guidance 和 Freshness 正确投影；
- 写成功后刷新权威 `context_revision`，陈旧写冲突后不保留 UI 假状态；
- Upgrade 与 Cleanup 均要求明确确认；Cleanup Token 陈旧时拒绝；
- 取消只在安全点生效；关闭窗口时仍保护正在提交的操作；
- V1 Import/Open/Edit/Refresh/Search/Export 回归通过；
- 无网络、无 AI、无新依赖运行。

Minimum automated coverage must verify:

- dual-view switching neither rebuilds nor damages Workspace Tree state;
- promotion is offered only for active, source-backed terminal files;
- preflight is read-only and matches execution-time capacity/source rules;
- promotion and Revision capture run in the background with a live GUI heartbeat;
- Section, Placement, Unsectioned, Guidance, and Freshness projections are correct;
- successful writes reload authoritative `context_revision`, while stale-write
  conflicts leave no false UI state;
- Upgrade and Cleanup require explicit confirmation, and stale cleanup tokens fail;
- cancellation occurs only at safe points, and window close still protects a
  committing operation;
- V1 Import/Open/Edit/Refresh/Search/Export regression remains green;
- operation is offline, AI-free, and dependency-free.

V2.1.4 完成标准是：用户能在现有桌面端从 Workspace 将文件加入 Context，在三栏视图中
分组、说明、查看 Freshness、创建新 Revision，并安全管理保护与清理；所有耗时操作不
冻结界面。真实大型 Project、磁盘不足和完整桌面人工验收仍属于 V2.1.5。

V2.1.4 is complete when a user can promote a Workspace file into Context,
organize and annotate it in the three-pane view, inspect freshness, create a new
Revision, and safely manage protection and cleanup without freezing the UI.
Real large Projects, low-disk scenarios, and full manual desktop acceptance
remain V2.1.5.

## 8. 当前授权门 / Current authorization gate

V2.1.4 已于 2026-10-08 按本计划完成实现和自动化回归。下一步只能在产品负责人单独
批准后进入 V2.1.5 Acceptance；内容解析、搜索索引、AI/RAG、MCP 和平台适配仍未授权。

V2.1.4 implementation and automated regression were completed according to this
plan on 2026-10-08. V2.1.5 Acceptance may begin only after separate product-owner
approval. Content extraction, search indexing, AI/RAG, MCP, and platform adapters
remain unauthorized.

## 9. 实施结果 / Implementation result

- 新增只读 Promote Preflight，执行前展示来源、预计大小、容量警告和阻断码；执行时仍由
  Application 层重新校验。
- 现有桌面窗口加入 `[Workspace] [Project Context]`，Workspace Tree 不重建。
- 独立 `context_view.py` 提供 Section、Item、Details 三栏 Qt Model/View。
- Promote、Section、Placement、Guidance、Revision、保护、清理和 Upgrade 均通过现有
  typed Application Contract；业务 Event 仍由 Application 层生成。
- 后台 Promote/Revision Capture 复用单执行器、进度和取消机制；冲突后重新读取权威状态。
- 没有新增 Schema、Migration、第三方依赖、内容解析或 AI 能力。

- A read-only promotion preflight now exposes source, estimated size, capacity
  warnings, and blocking codes before confirmation; execution still revalidates
  inside the Application layer.
- The existing desktop window now provides `[Workspace] [Project Context]`
  without rebuilding the Workspace Tree.
- A dedicated `context_view.py` provides the Section, Item, and Details panes
  using Qt Model/View.
- Promotion, Section, Placement, Guidance, Revision, protection, cleanup, and
  Upgrade use existing typed Application contracts; business Events remain
  Application-owned.
- Background promotion and Revision capture reuse the single executor, progress,
  and cancellation mechanism; conflicts reload authoritative state.
- No schema, migration, third-party dependency, content extraction, or AI
  capability was added.

自动化证据 / Automated evidence:

- V2.1.1–V2.1.4、对象存储与关键桌面回归：`40 passed`。
- 全部桌面 UI 回归：`17 passed, 4 skipped`；跳过项为 ADR-010 已取代的历史契约。
- 全部非 UI 回归：`189 passed, 91 skipped, 1 warning`；在支持原子目录重命名的
  系统临时目录运行。D 盘测试目录会被主机策略间歇阻止 `os.replace`，不属于断言失败。
- Python 编译检查与 `git diff --check`：通过。

- V2.1.1–V2.1.4, object-store, and key desktop regression: `40 passed`.
- Complete desktop UI regression: `17 passed, 4 skipped`; skipped cases are
  historical contracts superseded by ADR-010.
- Complete non-UI regression: `189 passed, 91 skipped, 1 warning`, run under the
  system temporary directory where atomic directory renames are supported. Host
  policy intermittently blocks `os.replace` in the D-drive test directory; this
  is not an assertion failure.
- Python compile check and `git diff --check`: passed.
