# ADR-031：导出 Container View 当前展开结构 / Export Current Expanded Container View

- 状态：已批准，待人工复测 / Status: Approved, pending manual retest
- 决策日期：2026-10-12 / Decision date: 2026-10-12

## 背景与决定 / Context and decision

此前 [ADR-019](ADR-019-workbench-project-layout-import-undo-folder-export.md) 只允许单个普通
Workspace 文件夹直接导出。用户在 V2.4 人工验收中明确选择：单选 ZIP/7z 等
`CONTAINER_VIEW` 时，导出其当前展开的文件结构，而不是导出原压缩包或自动重打包为原格式。
此决定仅扩展现有 `export_workspace_items` Action 的可选根节点类型，不改变容器来源字节。

[ADR-019](ADR-019-workbench-project-layout-import-undo-folder-export.md) previously allowed direct
directory export only for an ordinary Workspace folder. During V2.4 manual acceptance, the owner
selected export of the current expanded structure of a ZIP/7z `CONTAINER_VIEW`, not export of the
original archive bytes or automatic repacking into the original format. This decision only
extends the eligible root kind of `export_workspace_items`; source Container bytes remain unchanged.

## 行为与边界 / Behavior and boundaries

- 单选 Container View 导出为目标上级目录中的 `<显示名>-展开` 普通目录；保留活跃子树的
  相对层级和空目录。多选仍使用 ZIP，选中 Container View 时包含其活跃子树。
- 导出使用当前 Working 文件字节；Virtual File 受控物化。缺失或无法读取时失败，
  不静默回退 Original。Original 和原压缩包不得修改或重打包。
- 目标必须在项目受管目录之外；已有目标目录不合并、不覆盖。沿用路径冲突、
  资源限制和结构化事件记录。
- 本决定不授权在 Container View 内新建普通工作区文件夹，也不实现压缩包回写。

- A single Container View exports to an ordinary `<display-name>-展开` directory under the chosen
  parent, preserving active relative hierarchy and empty directories. Multi-selection still
  produces a ZIP and includes an active Container View subtree when selected.
- Export uses current Working bytes; virtual files are materialized under control. Missing or
  unreadable content fails rather than silently falling back to Original. Neither Original nor
  the source archive is changed or repacked.
- The destination must be outside the managed Project directory. Existing destination
  directories are neither merged nor overwritten. Path-collision checks, resource limits, and
  structured events continue to apply.
- This does not authorize creating ordinary Workspace folders inside a Container View or writing
  changes back into an archive.
