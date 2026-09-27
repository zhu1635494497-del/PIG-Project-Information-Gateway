# PIG V1 当前规划索引 / PIG V1 Active Planning Index

- 当前日期：2026-09-27 / Date: 2026-09-27
- 当前阶段：Workbench W10.5 自动资格 Gate 与源码桌面复验已通过；RC.2 等待最终打包桌面人工验收 / Current phase: Workbench W10.5 automated qualification gates and source-desktop re-acceptance pass; RC.2 is pending final-package manual desktop acceptance
- 代码授权：W1–W10；D92–D100 已批准，正式外发仍受人工 Gate 约束 / Code authorization: W1-W10; D92-D100 approved, with official distribution still gated by human review

## 当前规范优先级 / Active authority order

1. `PIG Project Rules.md`
2. `docs/DOCUMENTATION-STYLE.md`（仅约束文档格式 / documentation format only）
3. `docs/decisions/ADR-010-v1-project-file-workbench-reset.md`
4. `docs/application/PIG-V1-workbench-scope.md`
5. `docs/domain/PIG-V1-workbench-domain-model.md`
6. `docs/domain/PIG-V1-workbench-state-machines.md`
7. `docs/application/PIG-V1-workbench-milestones.md`
8. `docs/application/PIG-V1-desktop-acceptance.md`
9. `docs/decisions/ADR-011-workbench-clean-schema-baseline.md`
10. `docs/application/PIG-V1-workbench-W1.md`
11. `docs/decisions/ADR-012-workbench-snapshot-import-boundary.md`
12. `docs/application/PIG-V1-workbench-W2.md`
13. `docs/decisions/ADR-013-workbench-structure-materialization-boundary.md`
14. `docs/application/PIG-V1-workbench-W3.md`
15. `docs/decisions/ADR-014-workbench-complex-container-boundary.md`
16. `docs/application/PIG-V1-workbench-W4.md`
17. `docs/decisions/ADR-015-workbench-mutable-tree-actions.md`
18. `docs/application/PIG-V1-workbench-W5.md`
19. `docs/decisions/ADR-016-workbench-stable-open-edit-reconciliation.md`
20. `docs/application/PIG-V1-workbench-W6.md`
21. `docs/decisions/ADR-017-workbench-desktop-ui-boundary.md`
22. `docs/application/PIG-V1-workbench-W7.md`
23. `docs/decisions/ADR-018-workbench-usability-closure.md`
24. `docs/application/PIG-V1-workbench-W7.1.md`
25. `docs/decisions/ADR-019-workbench-project-layout-import-undo-folder-export.md`
26. `docs/application/PIG-V1-workbench-W7.2.md`
27. `docs/decisions/ADR-020-workbench-recovery-performance-packaging-reset.md`
28. `docs/application/PIG-V1-workbench-W8.md`
29. `docs/decisions/ADR-021-v1-release-qualification.md`
30. `docs/application/PIG-V1-workbench-W9.md`
31. `docs/decisions/ADR-022-v1-performance-responsiveness-stabilization.md`
32. `docs/application/PIG-V1-workbench-W10.md`
33. `docs/decisions/ADR-023-project-information-gateway-identity.md`

`ADR-023` 已接受，D100-B 已批准。正式产品身份改为
**PIG — Project Information Gateway**；Python import `pig`、`pig-desktop`、
`PIG.exe`、数据库 Schema 和已发布的 `v1.0.0-rc.1` 历史身份保持不变。长期概念
**PIG — Project Information Graph** 继续保留。

`ADR-023` is accepted and D100-B is approved. The official product identity is
now **PIG — Project Information Gateway**. Python import `pig`, `pig-desktop`,
`PIG.exe`, the database schema, and the published historical identity of
`v1.0.0-rc.1` remain unchanged. The long-term concept
**PIG — Project Information Graph** also remains.

`docs/decisions/ADR-022-v1-performance-responsiveness-stabilization.md` 已接受，
D92–D99 已批准。W10 在 `v1优化` 分支、基线 Commit
`0a9de407cfbc2c209dc3e10259f01d845365230a` 上按 W10.1 至 W10.5 顺序实施；
`v1.0.0-rc.1` 保持不变，通过性能与人工桌面验收后才可建立 `v1.0.0-rc.2`。

`docs/decisions/ADR-022-v1-performance-responsiveness-stabilization.md` is
accepted and D92-D99 are approved. W10 is implemented sequentially from W10.1
through W10.5 on branch `v1优化`, based on commit
`0a9de407cfbc2c209dc3e10259f01d845365230a`. `v1.0.0-rc.1` remains immutable;
`v1.0.0-rc.2` may be created only after performance and manual desktop
acceptance pass.

`docs/decisions/ADR-021-v1-release-qualification.md` 已接受，D78–D91 已批准。W9 可以
实施本地 Git、公开仓库准备、CI 和 Unsigned Internal RC；首次公开 Push 仍需精确文件
清单与最终确认，正式 V1 Release 仍需完成 License、Signing、Clean-host、真实 RAR 和
最终 Package Desktop Acceptance。

`docs/decisions/ADR-021-v1-release-qualification.md` is accepted and D78-D91 are
approved. W9 may implement local Git, public-repository preparation, CI, and an
unsigned Internal RC. The exact inventory and final confirmation remain required
before the first public push, and an official V1 Release still requires license,
signing, clean-host, real-RAR, and final-package desktop gates.

`ADR-020` 已接受。W8 自动实现、当前 Windows 主机机器验收和源码桌面人工验收已完成；
最终包与干净 Windows 主机发布资格验证转入 W9。

`ADR-020` is accepted. W8 automated implementation, current-host machine
acceptance, and source-desktop manual acceptance are complete. Final-package and
clean-Windows-host release qualification move to W9.

如果历史文档与上述当前文档冲突，以当前 Workbench 文档为准。

If a historical document conflicts with an active document above, the active
Workbench document controls.

## 历史实现记录 / Historical implementation record

ADR-001 至 ADR-009、原领域/持久化规范以及 Milestone 3–10 描述当前已经实现的
证据导向系统。它们仍可用于代码考古和识别可复用组件，但不定义目标 V1
Workbench 产品。

ADR-001 through ADR-009, the original domain/persistence specifications, and
Milestones 3-10 explain the currently implemented evidence-oriented application.
They remain useful for code archaeology and identifying reusable components, but
they do not define the target V1 Workbench product.

## 已批准决策 / Approved decisions

- D17-B：复杂项目文件 Workbench 优先；
  complex project file Workbench focus.
- D18-B：项目内不可变 Original Snapshot；
  immutable Project-owned Original Snapshot.
- D19-B：不可变 Source Structure 加可变 Workspace Tree；
  immutable Source Structure plus mutable Workspace Tree.
- D20-B：主动结构检查加终端文件延迟物化；
  eager structure inspection plus lazy terminal materialization.
- D21-B：稳定可编辑 Working File 加确定性刷新；
  stable externally editable Working File plus deterministic refresh.
- D22-B：Workspace Overlay，不回写 Container；
  Workspace overlay with no Container write-back.
- D23-B：可恢复的 Workspace 软删除；
  reversible Workspace soft delete.
- D25-B：新 `0001_workbench` 干净 Schema 基线；
  new clean `0001_workbench` schema baseline.
- D26-A：生成标识 Original Layout 加显式 Snapshot Entry Tree；
  generated-identity Original layout plus explicit Snapshot Entry tree.
- D27-B：Import Session 跨 W2–W3，W2 成功停在 `INSPECTING`；
  Import Session spans W2-W3 and successful W2 capture ends at `INSPECTING`.
- D28-A：W2 创建 Snapshot-backed Source 与 Root Node；
  W2 creates the snapshot-backed Source and root Node.
- D29-A：每个顶层 Snapshot 严格完整，Sibling 可继续；
  strict completeness per top-level snapshot while siblings continue.
- D30-B：Workbench-native `inspect/materialize` Handler Contract；
  Workbench-native `inspect/materialize` Handler contract.
- D31-A：Direct Relationship 使用显式 typed Entry Locator；
  explicit typed Entry Locators on direct relationships.
- D32-A：Source Structure 完整投影为初始 Workspace Tree；
  full Source Structure projection into the initial Workspace Tree.
- D33-A：生成标识 Working Layout 与可信 Suffix；
  generated-identity Working layout with trusted suffixes.
- D34-A：Operation-scoped Inspection Cache 与 Recipe Replay；
  operation-scoped inspection cache and recipe replay.
- D35-A：独立 typed Inspection 与 Materialization Action；
  separate typed inspection and materialization actions.
- D36-A：`0003_structure_workspace` 前向 Migration；
  forward `0003_structure_workspace` migration.
- D37-A：单表显式 typed Complex-container Locator；
  explicit typed complex-container locators in one table.
- D38-A：Backend Identity 持久化到 `ProcessingAttempt`；
  backend identity persisted on `ProcessingAttempt`.
- D39-A：可用字节使用 Archive Signature-first Detection；
  archive signature-first detection when bytes are available.
- D40-A：`0004_complex_containers` 前向 Migration；
  forward `0004_complex_containers` migration.
- D41-A：Active Sibling 连续 Ordinal 与原子 Move/Reorder；
  dense active-sibling ordinals and atomic move/reorder.
- D42-A：Project 级 `workspace_revision` Optimistic Concurrency；
  Project-scoped `workspace_revision` optimistic concurrency.
- D43-A：根 Tombstone 与后代有效隐藏；
  root tombstone with effective descendant hiding.
- D44-A：Import Session 持久化定向 Add Target；
  targeted Add destination persisted on Import Session.
- D45-A：Logical Segment Name，允许同级重名；
  logical-segment names with same-parent duplicates allowed.
- D46-A：`0005_workspace_actions` 前向 Migration；
  forward `0005_workspace_actions` migration.
- D47-A：统一 Open Action，Virtual 先物化、Materialized 先刷新；
  unified Open action with materialization for Virtual and refresh for Materialized.
- D48-A：`CHECKING` 仅为操作态，直接持久化最终 Content Status；
  operation-only `CHECKING` with direct final content-status persistence.
- D49-A：格式 Allowlist 加 OS 默认 File Association；
  format allowlist plus host default file association.
- D50-A：显式 Restore、覆盖确认与非普通路径永不替换；
  explicit restore, overwrite confirmation, and no replacement of non-regular paths.
- D51-A：显式 Refresh Reason、变化 Event 去重、每次 Open Attempt 留痕；
  explicit refresh reasons, deduplicated change Events, and every Open attempt recorded.
- D52-A：复用现有 Working 字段、受限 Hash、不增加 `0006`；
  reuse existing Working fields, bounded hashing, and no `0006` migration.
- D53-A：单窗口 Workspace-first Workbench；
  one-window Workspace-first Workbench.
- D54-A：typed Workspace Read Model Query；
  typed Workspace read-model queries.
- D55-A：多路径 Add 自动 Snapshot/Inspect；
  multi-path Add with automatic snapshot/inspection.
- D56-A：后端权威的 Tree Drag/Drop Move/Reorder；
  backend-authoritative tree drag/drop move/reorder.
- D57-A：独立 Deleted Items Restore 入口；
  separate Deleted Items restore surface.
- D58-A：W6 Open/Refresh/Restore 桌面接入与选中项 Focus Refresh；
  desktop W6 open/refresh/restore with selected-item focus refresh.
- D59-A：Workspace Search 与结果直接打开；
  Workspace Search with direct result Open.
- D60-A：单后台 Action Busy Policy，不增加 Migration；
  single-background-action busy policy with no migration.
- D61-A：中央 Workbench 全区域外部拖入，非 Tree 定向目标进入 Project Root；
  central Workbench external drop surface with non-Tree drops targeting Project Root.
- D62-A：只保留当前与上一 Working 版本，Original Baseline 独立保留；
  current and one previous Working version with a separate Original Baseline.
- D63-A：生成 Item 目录中的安全友好 Working 文件名与同名事前警告；
  safe friendly Working filename under a generated Item directory with pre-handoff duplicate warning.
- D64-A：单文件直接导出，多文件按 Workspace 相对路径导出 ZIP；
  direct single-file export and multi-file ZIP export using Workspace-relative paths.
- D65-A：新 Project 使用所选父目录下的合法 Project 名称目录；
  new Projects use a valid Project-name directory under the selected parent.
- D66-B（收紧）：按顶层 Import Item 撤销误导入，不建设任意节点硬删除；
  undo an accidental top-level Import Item without arbitrary-node hard deletion.
- D67-A：右键上下文菜单与 Toolbar 并存；
  context menus coexist with the toolbar.
- D68-A：单个 Workspace 文件夹导出为保留结构的普通目录；
  one Workspace folder exports as an ordinary structure-preserving directory.
- D92-A：保持 `v1.0.0-rc.1` 不变，W10 通过后建立 `v1.0.0-rc.2`；
  keep `v1.0.0-rc.1` immutable and create `v1.0.0-rc.2` only after W10 passes.
- D93-A：Set-based SQL Read Model，加数据库过滤、排序、分页和批量关联加载；
  set-based SQL read model with database filtering, sorting, paging, and batched relations.
- D94-A：`QTreeView + QAbstractItemModel` 按需加载与受影响分支增量刷新；
  lazy `QTreeView + QAbstractItemModel` with affected-branch incremental refresh.
- D95-A：同一 Source 事务中的有界批量 Repository 写入；
  bounded bulk repository writes inside one Source transaction.
- D96-A：单 Worker、串行写、Typed Progress 和安全点协作取消；
  one worker, serialized writes, typed progress, and cooperative safe-point cancellation.
- D97-A：保留不可变 Original、Copy+SHA、主动结构发现和终端延迟物化；
  retain immutable Originals, copy-plus-hash, eager structure discovery, and lazy terminal materialization.
- D98-A：允许只增加经 Query Plan 和 Benchmark 证明的 `0009` 索引；
  allow only query-plan- and benchmark-proven indexes in migration `0009`.
- D99-A：使用固定 Fixture、三轮中位数、Peak RSS、SQLite 大小和 UI 心跳验收；
  qualify with fixed fixtures, three-run medians, peak RSS, SQLite size, and UI heartbeat.
- D100-B：完整改名为 `PIG — Project Information Gateway`，保留内部稳定技术标识和
  已发布 RC.1 历史；fully rename the product to
  `PIG — Project Information Gateway` while retaining stable internal technical
  identifiers and published RC.1 history.

旧 Project 兼容性明确不在范围内。由于产品负责人指示无需考虑 D24，因此这里不
记录任何 D24 选项。

Existing Project compatibility is explicitly outside scope. This is not recorded
as a D24 option because the owner instructed that D24 need not be considered.

## 当前授权门 / Current authorization gate

产品负责人已批准 W10 D92-A 至 D99-A。W10 只能按 W10.1 至 W10.5 分阶段优化既有
V1 Read、Import/Processing、Export、Progress/Cancel 和资格验证闭环；不得改变
Original/Working 所有权、扩展到 V2、引入分布式 Worker 或绕过 W9 的人工发布 Gate。

The owner approved W10 D92-A through D99-A. W10 may optimize only the existing
V1 read, import/processing, export, progress/cancel, and qualification loops,
sequentially from W10.1 through W10.5. It must not change Original/Working
ownership, expand into V2, introduce distributed workers, or bypass W9 human
release gates.
